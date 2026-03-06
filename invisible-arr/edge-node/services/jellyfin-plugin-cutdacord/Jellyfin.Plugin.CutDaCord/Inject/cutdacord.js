(function () {
    'use strict';

    // Guard against double-loading
    if (window.__cutdacord_loaded) return;
    window.__cutdacord_loaded = true;

    /* ------------------------------------------------------------------ */
    /*  Constants                                                          */
    /* ------------------------------------------------------------------ */

    const API_BASE = (window.__CUTDACORD_API__ || 'https://api.cutdacord.app').replace(/\/$/, '');
    const STORAGE_KEY = 'cutdacord_api_key';
    const TMDB_IMG = 'https://image.tmdb.org/t/p';

    /* ------------------------------------------------------------------ */
    /*  Utility helpers                                                     */
    /* ------------------------------------------------------------------ */

    function waitForElement(selector, timeout) {
        if (timeout === undefined) timeout = 5000;
        return new Promise(function (resolve) {
            var el = document.querySelector(selector);
            if (el) { resolve(el); return; }
            var observer = new MutationObserver(function () {
                var found = document.querySelector(selector);
                if (found) { observer.disconnect(); resolve(found); }
            });
            observer.observe(document.body, { childList: true, subtree: true });
            setTimeout(function () { observer.disconnect(); resolve(null); }, timeout);
        });
    }

    /**
     * Validate a URL string against a list of allowed prefixes.
     * Returns the URL if valid, empty string otherwise.
     */
    function sanitizeImageUrl(url, allowedPrefixes) {
        if (typeof url !== 'string') return '';
        for (var i = 0; i < allowedPrefixes.length; i++) {
            if (url.indexOf(allowedPrefixes[i]) === 0) return url;
        }
        return '';
    }

    /* ------------------------------------------------------------------ */
    /*  Toast notifications                                                */
    /* ------------------------------------------------------------------ */

    function showToast(message, type) {
        if (!type) type = 'success';
        var toast = document.createElement('div');
        toast.className = 'cutdacord-toast cutdacord-toast--' + type;
        toast.textContent = message;
        toast.setAttribute('role', 'alert');
        document.body.appendChild(toast);

        // Trigger reflow for CSS transition
        void toast.offsetWidth;
        toast.classList.add('cutdacord-toast--visible');

        setTimeout(function () {
            toast.classList.remove('cutdacord-toast--visible');
            setTimeout(function () {
                if (toast.parentNode) toast.parentNode.removeChild(toast);
            }, 300);
        }, 3000);
    }

    /* ------------------------------------------------------------------ */
    /*  Authentication                                                     */
    /* ------------------------------------------------------------------ */

    var _authInProgress = null;

    function getApiKey() {
        return localStorage.getItem(STORAGE_KEY);
    }

    function setApiKey(key) {
        localStorage.setItem(STORAGE_KEY, key);
    }

    function clearApiKey() {
        localStorage.removeItem(STORAGE_KEY);
    }

    /**
     * Authenticate with CutDaCord backend using the current Jellyfin session.
     * Returns the API key or null on failure.
     */
    function authenticate() {
        // Deduplicate concurrent auth attempts
        if (_authInProgress) return _authInProgress;

        _authInProgress = _doAuthenticate().then(function (key) {
            _authInProgress = null;
            return key;
        }).catch(function (err) {
            _authInProgress = null;
            throw err;
        });

        return _authInProgress;
    }

    function _doAuthenticate() {
        return new Promise(function (resolve) {
            // Wait for ApiClient to be available
            if (typeof ApiClient === 'undefined') {
                resolve(null);
                return;
            }

            var token = ApiClient.accessToken();
            if (!token) { resolve(null); return; }

            ApiClient.getCurrentUser().then(function (user) {
                if (!user || !user.Id) { resolve(null); return; }

                var payload = {
                    jellyfin_user_id: user.Id,
                    jellyfin_username: user.Name || '',
                    jellyfin_token: token
                };

                fetch(API_BASE + '/v1/auth/jellyfin-login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                }).then(function (resp) {
                    if (!resp.ok) {
                        console.warn('[CutDaCord] Auth failed:', resp.status);
                        resolve(null);
                        return;
                    }
                    return resp.json();
                }).then(function (data) {
                    if (data && data.api_key) {
                        setApiKey(data.api_key);
                        resolve(data.api_key);
                    } else {
                        resolve(null);
                    }
                }).catch(function (err) {
                    console.warn('[CutDaCord] Auth error:', err);
                    resolve(null);
                });
            }).catch(function () {
                resolve(null);
            });
        });
    }

    /* ------------------------------------------------------------------ */
    /*  API helper                                                         */
    /* ------------------------------------------------------------------ */

    /**
     * Call the CutDaCord API. Automatically retries once on 401 by re-authing.
     */
    function api(method, path, body, _isRetry) {
        var apiKey = getApiKey();

        // If no key yet, auth first
        if (!apiKey && !_isRetry) {
            return authenticate().then(function () {
                return api(method, path, body, false);
            });
        }

        var opts = {
            method: method,
            headers: {
                'Content-Type': 'application/json'
            }
        };

        if (apiKey) {
            opts.headers['X-Api-Key'] = apiKey;
        }

        if (body !== undefined && body !== null) {
            opts.body = JSON.stringify(body);
        }

        return fetch(API_BASE + path, opts).then(function (resp) {
            if (resp.status === 401 && !_isRetry) {
                clearApiKey();
                return authenticate().then(function () {
                    return api(method, path, body, true);
                });
            }
            if (!resp.ok) {
                return resp.text().then(function (text) {
                    console.warn('[CutDaCord] API error', resp.status, text);
                    return null;
                });
            }
            var ct = resp.headers.get('content-type') || '';
            if (ct.indexOf('application/json') !== -1) {
                return resp.json();
            }
            return null;
        }).catch(function (err) {
            console.warn('[CutDaCord] API fetch error:', err);
            return null;
        });
    }

    /* ------------------------------------------------------------------ */
    /*  Detail-page route detection                                        */
    /* ------------------------------------------------------------------ */

    var _lastHandledUrl = '';

    function extractItemId(url) {
        if (!url) url = window.location.hash || window.location.href;
        // Match #/details?id=XXX or #/item?id=XXX (also with extra params)
        var match = url.match(/[#/](?:details|item)\?.*?id=([a-f0-9]+)/i);
        return match ? match[1] : null;
    }

    function onRouteChange() {
        var currentUrl = window.location.hash || window.location.href;
        if (currentUrl === _lastHandledUrl) return;
        _lastHandledUrl = currentUrl;

        var itemId = extractItemId(currentUrl);
        if (itemId) {
            handleDetailPage(itemId);
        }
    }

    // Monkey-patch history methods to detect SPA navigation
    function patchHistory(methodName) {
        var original = history[methodName];
        history[methodName] = function () {
            var result = original.apply(this, arguments);
            onRouteChange();
            return result;
        };
    }

    patchHistory('pushState');
    patchHistory('replaceState');
    window.addEventListener('hashchange', onRouteChange);
    window.addEventListener('popstate', onRouteChange);

    /* ------------------------------------------------------------------ */
    /*  Detail page — Request button injection                             */
    /* ------------------------------------------------------------------ */

    function handleDetailPage(itemId) {
        if (typeof ApiClient === 'undefined') return;

        ApiClient.getCurrentUser().then(function (user) {
            if (!user || !user.Id) return;

            ApiClient.getItem(user.Id, itemId).then(function (item) {
                if (!item) return;

                var tmdbId = item.ProviderIds && item.ProviderIds.Tmdb;
                if (!tmdbId) return;

                var mediaType = null;
                if (item.Type === 'Movie') mediaType = 'movie';
                else if (item.Type === 'Series') mediaType = 'tv';
                else return;

                injectRequestButton(item, tmdbId, mediaType);
            }).catch(function (err) {
                console.warn('[CutDaCord] Failed to fetch item:', err);
            });
        });
    }

    function injectRequestButton(item, tmdbId, mediaType) {
        waitForElement('.mainDetailButtons, .detailButtons').then(function (container) {
            if (!container) return;

            // Don't duplicate
            if (container.querySelector('.cutdacord-request-btn')) return;

            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'cutdacord-request-btn raised-mini-button';
            btn.setAttribute('is', 'emby-button');

            var icon = document.createElement('span');
            icon.className = 'material-icons cutdacord-btn-icon';
            icon.textContent = 'add_circle';

            var label = document.createElement('span');
            label.textContent = 'Request';

            btn.appendChild(icon);
            btn.appendChild(label);

            btn.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopPropagation();
                openRequestModal(item, tmdbId, mediaType);
            });

            container.appendChild(btn);
        });
    }

    /* ------------------------------------------------------------------ */
    /*  Request Modal                                                       */
    /* ------------------------------------------------------------------ */

    function openRequestModal(item, tmdbId, mediaType) {
        // Remove any existing modal
        closeRequestModal();

        var overlay = document.createElement('div');
        overlay.className = 'cutdacord-modal-overlay';
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) closeRequestModal();
        });

        var modal = document.createElement('div');
        modal.className = 'cutdacord-modal';
        modal.setAttribute('role', 'dialog');
        modal.setAttribute('aria-modal', 'true');

        // Header
        var header = document.createElement('div');
        header.className = 'cutdacord-modal-header';

        var posterContainer = document.createElement('div');
        posterContainer.className = 'cutdacord-modal-poster';

        if (typeof ApiClient !== 'undefined' && item.Id) {
            var posterUrl = ApiClient.getImageUrl(item.Id, { type: 'Primary', maxWidth: 185 });
            var validatedUrl = sanitizeImageUrl(posterUrl, [
                window.location.origin,
                'http://localhost',
                'http://127.0.0.1',
                TMDB_IMG
            ]);
            if (validatedUrl) {
                var posterImg = document.createElement('img');
                posterImg.src = validatedUrl;
                posterImg.alt = '';
                posterImg.className = 'cutdacord-poster-img';
                posterContainer.appendChild(posterImg);
            }
        }

        var titleEl = document.createElement('div');
        titleEl.className = 'cutdacord-modal-title';

        var titleText = document.createElement('h2');
        titleText.textContent = item.Name || 'Unknown Title';
        titleEl.appendChild(titleText);

        if (item.ProductionYear) {
            var yearSpan = document.createElement('span');
            yearSpan.className = 'cutdacord-modal-year';
            yearSpan.textContent = '(' + item.ProductionYear + ')';
            titleEl.appendChild(yearSpan);
        }

        if (item.Overview) {
            var overview = document.createElement('p');
            overview.className = 'cutdacord-modal-overview';
            // Truncate long overviews
            var overviewText = item.Overview.length > 200
                ? item.Overview.substring(0, 200) + '...'
                : item.Overview;
            overview.textContent = overviewText;
            titleEl.appendChild(overview);
        }

        header.appendChild(posterContainer);
        header.appendChild(titleEl);

        // Close button
        var closeBtn = document.createElement('button');
        closeBtn.type = 'button';
        closeBtn.className = 'cutdacord-modal-close';
        closeBtn.textContent = '\u00D7'; // multiplication sign (x)
        closeBtn.setAttribute('aria-label', 'Close');
        closeBtn.addEventListener('click', closeRequestModal);
        header.appendChild(closeBtn);

        modal.appendChild(header);

        // Body
        var body = document.createElement('div');
        body.className = 'cutdacord-modal-body';

        // Acquisition mode
        var modeGroup = buildAcquisitionModeGroup();
        body.appendChild(modeGroup);

        if (mediaType === 'movie') {
            buildMovieForm(body, item, tmdbId, modeGroup);
        } else {
            buildTvForm(body, item, tmdbId, modeGroup);
        }

        modal.appendChild(body);
        overlay.appendChild(modal);
        document.body.appendChild(overlay);

        // Trap escape key
        overlay._keyHandler = function (e) {
            if (e.key === 'Escape') closeRequestModal();
        };
        document.addEventListener('keydown', overlay._keyHandler);
    }

    function closeRequestModal() {
        var overlay = document.querySelector('.cutdacord-modal-overlay');
        if (overlay) {
            if (overlay._keyHandler) {
                document.removeEventListener('keydown', overlay._keyHandler);
            }
            overlay.parentNode.removeChild(overlay);
        }
    }

    /* ------------------------------------------------------------------ */
    /*  Acquisition mode radio group                                       */
    /* ------------------------------------------------------------------ */

    function buildAcquisitionModeGroup() {
        var group = document.createElement('div');
        group.className = 'cutdacord-mode-group';

        var legend = document.createElement('div');
        legend.className = 'cutdacord-mode-legend';
        legend.textContent = 'Acquisition Mode';
        group.appendChild(legend);

        var radioContainer = document.createElement('div');
        radioContainer.className = 'cutdacord-mode-radios';

        var modes = [
            { value: 'download', label: 'Download' },
            { value: 'stream', label: 'Stream' }
        ];

        for (var i = 0; i < modes.length; i++) {
            var wrapper = document.createElement('label');
            wrapper.className = 'cutdacord-radio-label';

            var radio = document.createElement('input');
            radio.type = 'radio';
            radio.name = 'cutdacord_acq_mode';
            radio.value = modes[i].value;
            radio.className = 'cutdacord-radio';
            if (i === 0) radio.checked = true;

            var span = document.createElement('span');
            span.textContent = modes[i].label;

            wrapper.appendChild(radio);
            wrapper.appendChild(span);
            radioContainer.appendChild(wrapper);
        }

        group.appendChild(radioContainer);
        return group;
    }

    function getSelectedMode() {
        var checked = document.querySelector('input[name="cutdacord_acq_mode"]:checked');
        return checked ? checked.value : 'download';
    }

    /* ------------------------------------------------------------------ */
    /*  Movie form                                                         */
    /* ------------------------------------------------------------------ */

    function buildMovieForm(body, item, tmdbId, modeGroup) {
        var submitBtn = document.createElement('button');
        submitBtn.type = 'button';
        submitBtn.className = 'cutdacord-submit-btn';
        submitBtn.textContent = 'Submit Request';

        submitBtn.addEventListener('click', function () {
            submitBtn.disabled = true;
            submitBtn.textContent = 'Submitting...';

            var payload = {
                tmdb_id: parseInt(tmdbId, 10),
                media_type: 'movie',
                query: item.Name || '',
                season: null,
                episode: null,
                acquisition_mode: getSelectedMode()
            };

            api('POST', '/v1/request', payload).then(function (result) {
                if (result) {
                    showToast('Movie requested successfully!', 'success');
                    closeRequestModal();
                } else {
                    showToast('Failed to submit request.', 'error');
                    submitBtn.disabled = false;
                    submitBtn.textContent = 'Submit Request';
                }
            });
        });

        body.appendChild(submitBtn);
    }

    /* ------------------------------------------------------------------ */
    /*  TV form (season selection)                                         */
    /* ------------------------------------------------------------------ */

    function buildTvForm(body, item, tmdbId, modeGroup) {
        var seasonsContainer = document.createElement('div');
        seasonsContainer.className = 'cutdacord-seasons-container';

        var loadingEl = document.createElement('div');
        loadingEl.className = 'cutdacord-loading';
        loadingEl.textContent = 'Loading seasons...';
        seasonsContainer.appendChild(loadingEl);

        body.appendChild(seasonsContainer);

        // Fetch seasons from CutDaCord API
        api('GET', '/v1/tmdb/tv/' + encodeURIComponent(tmdbId) + '/seasons').then(function (data) {
            // Clear loading
            seasonsContainer.textContent = '';

            if (!data || !data.seasons || data.seasons.length === 0) {
                var noSeasons = document.createElement('p');
                noSeasons.className = 'cutdacord-no-seasons';
                noSeasons.textContent = 'No season information available.';
                seasonsContainer.appendChild(noSeasons);
                return;
            }

            var seasons = data.seasons;

            // Section label
            var sectionLabel = document.createElement('div');
            sectionLabel.className = 'cutdacord-section-label';
            sectionLabel.textContent = 'Select Seasons';
            seasonsContainer.appendChild(sectionLabel);

            // "All Seasons" toggle
            var allWrapper = document.createElement('label');
            allWrapper.className = 'cutdacord-checkbox-label cutdacord-checkbox-all';

            var allCheck = document.createElement('input');
            allCheck.type = 'checkbox';
            allCheck.className = 'cutdacord-checkbox';
            allCheck.dataset.allToggle = 'true';

            var allSpan = document.createElement('span');
            allSpan.textContent = 'All Seasons';

            allWrapper.appendChild(allCheck);
            allWrapper.appendChild(allSpan);
            seasonsContainer.appendChild(allWrapper);

            // Individual season checkboxes
            var checkboxList = document.createElement('div');
            checkboxList.className = 'cutdacord-season-list';

            var seasonCheckboxes = [];

            for (var i = 0; i < seasons.length; i++) {
                var season = seasons[i];
                // Skip specials (season 0) unless it's the only one
                var seasonNum = season.season_number !== undefined ? season.season_number : (i + 1);

                var wrapper = document.createElement('label');
                wrapper.className = 'cutdacord-checkbox-label';

                var cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.className = 'cutdacord-checkbox cutdacord-season-cb';
                cb.value = String(seasonNum);

                var cbSpan = document.createElement('span');
                cbSpan.textContent = season.name || ('Season ' + seasonNum);

                wrapper.appendChild(cb);
                wrapper.appendChild(cbSpan);
                checkboxList.appendChild(wrapper);
                seasonCheckboxes.push(cb);
            }

            seasonsContainer.appendChild(checkboxList);

            // "All" toggle behaviour
            allCheck.addEventListener('change', function () {
                for (var j = 0; j < seasonCheckboxes.length; j++) {
                    seasonCheckboxes[j].checked = allCheck.checked;
                }
            });

            // Uncheck "all" if any individual is unchecked
            checkboxList.addEventListener('change', function () {
                var allChecked = true;
                for (var j = 0; j < seasonCheckboxes.length; j++) {
                    if (!seasonCheckboxes[j].checked) { allChecked = false; break; }
                }
                allCheck.checked = allChecked;
            });

            // Submit button
            var submitBtn = document.createElement('button');
            submitBtn.type = 'button';
            submitBtn.className = 'cutdacord-submit-btn';
            submitBtn.textContent = 'Submit Request';

            submitBtn.addEventListener('click', function () {
                var selectedSeasons = [];
                for (var j = 0; j < seasonCheckboxes.length; j++) {
                    if (seasonCheckboxes[j].checked) {
                        selectedSeasons.push(parseInt(seasonCheckboxes[j].value, 10));
                    }
                }

                if (selectedSeasons.length === 0) {
                    showToast('Please select at least one season.', 'warn');
                    return;
                }

                submitBtn.disabled = true;
                submitBtn.textContent = 'Submitting...';

                var payload = {
                    tmdb_id: parseInt(tmdbId, 10),
                    query: item.Name || '',
                    seasons: selectedSeasons,
                    acquisition_mode: getSelectedMode()
                };

                api('POST', '/v1/request/batch', payload).then(function (result) {
                    if (result) {
                        showToast('TV request submitted!', 'success');
                        closeRequestModal();
                    } else {
                        showToast('Failed to submit request.', 'error');
                        submitBtn.disabled = false;
                        submitBtn.textContent = 'Submit Request';
                    }
                });
            });

            body.appendChild(submitBtn);
        });
    }

    /* ------------------------------------------------------------------ */
    /*  Initialisation                                                     */
    /* ------------------------------------------------------------------ */

    function init() {
        // Authenticate on load
        authenticate().then(function (key) {
            if (key) {
                console.log('[CutDaCord] Authenticated successfully.');
            } else {
                console.warn('[CutDaCord] Auth deferred — will retry on first API call.');
            }
        });

        // Check if we're already on a detail page
        onRouteChange();
    }

    // Wait for ApiClient to be ready before initialising
    if (typeof ApiClient !== 'undefined') {
        init();
    } else {
        // Jellyfin loads ApiClient asynchronously; poll briefly
        var _initAttempts = 0;
        var _initInterval = setInterval(function () {
            _initAttempts++;
            if (typeof ApiClient !== 'undefined') {
                clearInterval(_initInterval);
                init();
            } else if (_initAttempts > 50) {
                // Give up after ~5 seconds
                clearInterval(_initInterval);
                console.warn('[CutDaCord] ApiClient not available. Plugin will not function.');
            }
        }, 100);
    }

})();
