(function () {
    'use strict';

    // Guard against double-loading
    if (window.__cutdacord_loaded) return;
    window.__cutdacord_loaded = true;

    // Low-power device detection
    (function detectLowPower() {
        if (/WebOS|webOS|LG Browser|iPhone OS 1[0-5]/i.test(navigator.userAgent)) {
            document.body.classList.add('cutdacord-lowpower');
        }
    })();

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
                injectDeleteButton(item, mediaType);
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

        var posterUrl = null;
        if (item._tmdbPoster) {
            posterUrl = sanitizeImageUrl(TMDB_IMG + '/w185' + item._tmdbPoster, [TMDB_IMG]);
        } else if (typeof ApiClient !== 'undefined' && item.Id) {
            posterUrl = sanitizeImageUrl(
                ApiClient.getImageUrl(item.Id, { type: 'Primary', maxWidth: 185 }),
                [window.location.origin, 'http://localhost', 'http://127.0.0.1', TMDB_IMG]
            );
        }
        if (posterUrl) {
            var posterImg = document.createElement('img');
            posterImg.src = posterUrl;
            posterImg.alt = '';
            posterImg.className = 'cutdacord-poster-img';
            posterContainer.appendChild(posterImg);
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
        var formContainer = document.createElement('div');
        formContainer.className = 'cutdacord-tv-form';

        var loadingEl = document.createElement('div');
        loadingEl.className = 'cutdacord-loading';
        loadingEl.textContent = 'Loading seasons...';
        formContainer.appendChild(loadingEl);
        body.appendChild(formContainer);

        api('GET', '/v1/tmdb/tv/' + encodeURIComponent(tmdbId) + '/seasons').then(function (data) {
            while (formContainer.firstChild) formContainer.removeChild(formContainer.firstChild);

            if (!data || !data.seasons || data.seasons.length === 0) {
                var noData = document.createElement('p');
                noData.textContent = 'No season info available';
                noData.style.color = 'rgba(255,255,255,0.5)';
                formContainer.appendChild(noData);
                return;
            }

            var seasons = data.seasons.filter(function (s) { return s.season_number > 0; });

            // Season dropdown
            var seasonLabel = document.createElement('div');
            seasonLabel.className = 'cutdacord-section-label';
            seasonLabel.textContent = 'Season';
            formContainer.appendChild(seasonLabel);

            var seasonSelect = document.createElement('select');
            seasonSelect.className = 'cutdacord-select';
            seasons.forEach(function (s) {
                var opt = document.createElement('option');
                opt.value = String(s.season_number);
                opt.textContent = s.name || ('Season ' + s.season_number);
                seasonSelect.appendChild(opt);
            });
            formContainer.appendChild(seasonSelect);

            // Radio: Full Season / Specific Episode
            var radioGroup = document.createElement('div');
            radioGroup.className = 'cutdacord-radio-group';

            var fullLabel = document.createElement('label');
            fullLabel.className = 'cutdacord-radio-label';
            var fullRadio = document.createElement('input');
            fullRadio.type = 'radio';
            fullRadio.name = 'cutdacord-ep-mode';
            fullRadio.value = 'full';
            fullRadio.checked = true;
            fullRadio.className = 'cutdacord-radio';
            var fullSpan = document.createElement('span');
            fullSpan.textContent = 'Full Season';
            fullLabel.appendChild(fullRadio);
            fullLabel.appendChild(fullSpan);
            radioGroup.appendChild(fullLabel);

            var epLabel = document.createElement('label');
            epLabel.className = 'cutdacord-radio-label';
            var epRadio = document.createElement('input');
            epRadio.type = 'radio';
            epRadio.name = 'cutdacord-ep-mode';
            epRadio.value = 'episode';
            epRadio.className = 'cutdacord-radio';
            var epSpan = document.createElement('span');
            epSpan.textContent = 'Specific Episode';
            epLabel.appendChild(epRadio);
            epLabel.appendChild(epSpan);
            radioGroup.appendChild(epLabel);

            formContainer.appendChild(radioGroup);

            // Episode dropdown (hidden by default)
            var epSection = document.createElement('div');
            epSection.className = 'cutdacord-episode-section';
            epSection.style.display = 'none';

            var epSelectLabel = document.createElement('div');
            epSelectLabel.className = 'cutdacord-section-label';
            epSelectLabel.textContent = 'Episode';
            epSection.appendChild(epSelectLabel);

            var epSelect = document.createElement('select');
            epSelect.className = 'cutdacord-select';
            epSection.appendChild(epSelect);
            formContainer.appendChild(epSection);

            // Load episodes when season changes or episode mode selected
            function loadSeasonEpisodes() {
                var seasonNum = parseInt(seasonSelect.value, 10);
                while (epSelect.firstChild) epSelect.removeChild(epSelect.firstChild);

                var loadOpt = document.createElement('option');
                loadOpt.textContent = 'Loading...';
                loadOpt.disabled = true;
                epSelect.appendChild(loadOpt);

                api('GET', '/v1/tmdb/tv/' + encodeURIComponent(tmdbId) + '/season/' + seasonNum).then(function (epData) {
                    while (epSelect.firstChild) epSelect.removeChild(epSelect.firstChild);
                    if (!epData || !epData.episodes) return;

                    epData.episodes.forEach(function (ep) {
                        var opt = document.createElement('option');
                        opt.value = String(ep.episode_number);
                        opt.textContent = 'E' + (ep.episode_number < 10 ? '0' : '') + ep.episode_number + ' - ' + (ep.name || 'Episode ' + ep.episode_number);
                        epSelect.appendChild(opt);
                    });
                });
            }

            // Toggle episode dropdown visibility
            fullRadio.addEventListener('change', function () { epSection.style.display = 'none'; });
            epRadio.addEventListener('change', function () {
                epSection.style.display = 'block';
                loadSeasonEpisodes();
            });
            seasonSelect.addEventListener('change', function () {
                if (epRadio.checked) loadSeasonEpisodes();
            });

            // Submit button
            var submitBtn = document.createElement('button');
            submitBtn.type = 'button';
            submitBtn.className = 'cutdacord-submit-btn';
            submitBtn.textContent = 'Submit Request';

            submitBtn.addEventListener('click', function () {
                var seasonNum = parseInt(seasonSelect.value, 10);
                submitBtn.disabled = true;
                submitBtn.textContent = 'Submitting...';

                if (epRadio.checked && epSelect.value) {
                    // Specific episode request
                    var epNum = parseInt(epSelect.value, 10);
                    api('POST', '/v1/request', {
                        tmdb_id: parseInt(tmdbId, 10),
                        media_type: 'tv',
                        query: item.Name || '',
                        season: seasonNum,
                        episode: epNum,
                        acquisition_mode: getSelectedMode()
                    }).then(function (result) {
                        if (result) {
                            showToast('Episode requested!', 'success');
                            closeRequestModal();
                        } else {
                            showToast('Failed to submit request.', 'error');
                            submitBtn.disabled = false;
                            submitBtn.textContent = 'Submit Request';
                        }
                    });
                } else {
                    // Full season request
                    api('POST', '/v1/request/batch', {
                        tmdb_id: parseInt(tmdbId, 10),
                        query: item.Name || '',
                        seasons: [seasonNum],
                        acquisition_mode: getSelectedMode()
                    }).then(function (result) {
                        if (result) {
                            showToast('Season requested!', 'success');
                            closeRequestModal();
                        } else {
                            showToast('Failed to submit request.', 'error');
                            submitBtn.disabled = false;
                            submitBtn.textContent = 'Submit Request';
                        }
                    });
                }
            });

            formContainer.appendChild(submitBtn);
        });
    }

    /* ------------------------------------------------------------------ */
    /*  Delete button on detail pages                                      */
    /* ------------------------------------------------------------------ */

    function injectDeleteButton(item, mediaType) {
        waitForElement('.mainDetailButtons, .detailButtons').then(function (container) {
            if (!container) return;
            if (container.querySelector('.cutdacord-delete-btn')) return;

            // Check if item is in user's library
            api('GET', '/v1/library?media_type=' + encodeURIComponent(mediaType)).then(function (data) {
                if (!data || !data.items || data.items.length === 0) return;

                // Match by title (folder name contains item name)
                var itemName = item.Name || '';
                var matchedItem = null;
                for (var i = 0; i < data.items.length; i++) {
                    var libItem = data.items[i];
                    if (libItem.title === itemName || libItem.folder.indexOf(itemName) !== -1) {
                        matchedItem = libItem;
                        break;
                    }
                }

                if (!matchedItem) return;

                // Re-check container still exists and no duplicate
                var freshContainer = document.querySelector('.mainDetailButtons, .detailButtons');
                if (!freshContainer || freshContainer.querySelector('.cutdacord-delete-btn')) return;

                var btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'cutdacord-delete-btn raised-mini-button';
                btn.setAttribute('is', 'emby-button');

                var icon = document.createElement('span');
                icon.className = 'material-icons cutdacord-btn-icon';
                icon.textContent = 'delete';

                var label = document.createElement('span');
                label.textContent = 'Remove';

                btn.appendChild(icon);
                btn.appendChild(label);

                btn.addEventListener('click', function (e) {
                    e.preventDefault();
                    e.stopPropagation();
                    openDeleteModal(item, matchedItem, mediaType);
                });

                freshContainer.appendChild(btn);
            });
        });
    }

    function openDeleteModal(item, libraryItem, mediaType) {
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

        var titleEl = document.createElement('div');
        titleEl.className = 'cutdacord-modal-title';

        var titleText = document.createElement('h2');
        titleText.textContent = 'Remove ' + (item.Name || 'this item') + '?';
        titleEl.appendChild(titleText);

        var sizeInfo = document.createElement('p');
        sizeInfo.className = 'cutdacord-modal-overview';
        var sizeGb = (libraryItem.size_bytes / (1024 * 1024 * 1024)).toFixed(2);
        sizeInfo.textContent = 'This will remove the file from your library (' + sizeGb + ' GB).';
        titleEl.appendChild(sizeInfo);

        header.appendChild(titleEl);

        var closeBtn = document.createElement('button');
        closeBtn.type = 'button';
        closeBtn.className = 'cutdacord-modal-close';
        closeBtn.textContent = '\u00D7';
        closeBtn.setAttribute('aria-label', 'Close');
        closeBtn.addEventListener('click', closeRequestModal);
        header.appendChild(closeBtn);

        modal.appendChild(header);

        // Body with scope options for TV
        var body = document.createElement('div');
        body.className = 'cutdacord-modal-body';

        var deleteScope = 'file';
        if (mediaType === 'tv') {
            var scopeGroup = document.createElement('div');
            scopeGroup.className = 'cutdacord-mode-group';

            var legend = document.createElement('div');
            legend.className = 'cutdacord-mode-legend';
            legend.textContent = 'What to remove';
            scopeGroup.appendChild(legend);

            var radioContainer = document.createElement('div');
            radioContainer.className = 'cutdacord-mode-radios';
            radioContainer.style.flexDirection = 'column';
            radioContainer.style.gap = '0.5rem';

            var scopes = [
                { value: 'file', label: 'This episode only' },
                { value: 'season', label: 'Entire season' },
                { value: 'series', label: 'Entire series' }
            ];

            for (var i = 0; i < scopes.length; i++) {
                var wrapper = document.createElement('label');
                wrapper.className = 'cutdacord-radio-label';

                var radio = document.createElement('input');
                radio.type = 'radio';
                radio.name = 'cutdacord_del_scope';
                radio.value = scopes[i].value;
                radio.className = 'cutdacord-radio';
                if (i === 0) radio.checked = true;

                var span = document.createElement('span');
                span.textContent = scopes[i].label;

                wrapper.appendChild(radio);
                wrapper.appendChild(span);
                radioContainer.appendChild(wrapper);
            }

            scopeGroup.appendChild(radioContainer);
            body.appendChild(scopeGroup);
        }

        // Delete button
        var deleteBtn = document.createElement('button');
        deleteBtn.type = 'button';
        deleteBtn.className = 'cutdacord-submit-btn cutdacord-delete-submit';
        deleteBtn.textContent = 'Remove from Library';

        deleteBtn.addEventListener('click', function () {
            deleteBtn.disabled = true;
            deleteBtn.textContent = 'Removing...';

            if (mediaType === 'tv') {
                var checked = document.querySelector('input[name="cutdacord_del_scope"]:checked');
                deleteScope = checked ? checked.value : 'file';
            } else {
                deleteScope = 'file';
            }

            var payload = {
                file_path: libraryItem.file_path,
                media_type: mediaType,
                delete_scope: deleteScope
            };

            api('DELETE', '/v1/library/item', payload).then(function (result) {
                if (result) {
                    showToast('Removed successfully! Freed ' + ((result.freed_bytes || 0) / (1024*1024*1024)).toFixed(2) + ' GB', 'success');
                    closeRequestModal();
                    // Remove the delete button since item is gone
                    var delBtn = document.querySelector('.cutdacord-delete-btn');
                    if (delBtn) delBtn.parentNode.removeChild(delBtn);
                } else {
                    showToast('Failed to remove item.', 'error');
                    deleteBtn.disabled = false;
                    deleteBtn.textContent = 'Remove from Library';
                }
            });
        });

        body.appendChild(deleteBtn);

        // Cancel button
        var cancelBtn = document.createElement('button');
        cancelBtn.type = 'button';
        cancelBtn.className = 'cutdacord-submit-btn';
        cancelBtn.style.background = 'rgba(255,255,255,0.08)';
        cancelBtn.style.marginTop = '0.5rem';
        cancelBtn.textContent = 'Cancel';
        cancelBtn.addEventListener('click', closeRequestModal);
        body.appendChild(cancelBtn);

        modal.appendChild(body);
        overlay.appendChild(modal);
        document.body.appendChild(overlay);

        overlay._keyHandler = function (e) {
            if (e.key === 'Escape') closeRequestModal();
        };
        document.addEventListener('keydown', overlay._keyHandler);
    }

    /* ------------------------------------------------------------------ */
    /*  TMDB Search Modal                                                  */
    /* ------------------------------------------------------------------ */

    var _searchPage = 1;
    var _searchQuery = '';
    var _searchTotal = 0;

    function injectSearchButton() {
        // Find the header nav area
        waitForElement('.headerRight, .skinHeader .headerButton').then(function (ref) {
            if (!ref) return;
            var container = ref.closest('.skinHeader') || ref.parentNode;
            if (!container || container.querySelector('.cutdacord-search-btn')) return;

            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'cutdacord-search-btn headerButton headerButtonRight';

            var icon = document.createElement('span');
            icon.className = 'material-icons';
            icon.textContent = 'library_add';
            icon.style.fontSize = '24px';

            btn.appendChild(icon);
            btn.title = 'Search & Request Media';
            btn.addEventListener('click', function (e) {
                e.preventDefault();
                e.stopPropagation();
                openSearchModal();
            });

            // Insert before the last few buttons in headerRight
            var headerRight = container.querySelector('.headerRight');
            if (headerRight) {
                headerRight.insertBefore(btn, headerRight.firstChild);
            } else {
                container.appendChild(btn);
            }
        });
    }

    function openSearchModal() {
        closeSearchModal();
        _searchPage = 1;
        _searchQuery = '';
        _searchTotal = 0;

        var overlay = document.createElement('div');
        overlay.className = 'cutdacord-search-overlay';
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) closeSearchModal();
        });

        var panel = document.createElement('div');
        panel.className = 'cutdacord-search-panel';

        // Header
        var hdr = document.createElement('div');
        hdr.className = 'cutdacord-search-header';

        var title = document.createElement('h2');
        title.textContent = 'Search & Request';
        hdr.appendChild(title);

        var closeBtn = document.createElement('button');
        closeBtn.type = 'button';
        closeBtn.className = 'cutdacord-modal-close';
        closeBtn.textContent = '\u00D7';
        closeBtn.setAttribute('aria-label', 'Close');
        closeBtn.addEventListener('click', closeSearchModal);
        hdr.appendChild(closeBtn);

        panel.appendChild(hdr);

        // Search box
        var searchBox = document.createElement('div');
        searchBox.className = 'cutdacord-search-box';

        var input = document.createElement('input');
        input.type = 'text';
        input.className = 'cutdacord-search-input';
        input.placeholder = 'Search movies & TV shows...';
        input.autocomplete = 'off';

        var searchIcon = document.createElement('span');
        searchIcon.className = 'material-icons cutdacord-search-icon';
        searchIcon.textContent = 'search';

        searchBox.appendChild(searchIcon);
        searchBox.appendChild(input);
        panel.appendChild(searchBox);

        // Results grid
        var grid = document.createElement('div');
        grid.className = 'cutdacord-search-grid';
        grid.id = 'cutdacord-search-grid';
        panel.appendChild(grid);

        // Navigation
        var nav = document.createElement('div');
        nav.className = 'cutdacord-search-nav';
        nav.id = 'cutdacord-search-nav';
        nav.style.display = 'none';

        var prevBtn = document.createElement('button');
        prevBtn.type = 'button';
        prevBtn.className = 'cutdacord-search-nav-btn';
        prevBtn.textContent = 'Previous';
        prevBtn.id = 'cutdacord-search-prev';
        prevBtn.addEventListener('click', function () {
            if (_searchPage > 1) {
                _searchPage--;
                performSearch(_searchQuery, _searchPage);
            }
        });

        var pageInfo = document.createElement('span');
        pageInfo.className = 'cutdacord-search-page-info';
        pageInfo.id = 'cutdacord-search-page-info';

        var nextBtn = document.createElement('button');
        nextBtn.type = 'button';
        nextBtn.className = 'cutdacord-search-nav-btn';
        nextBtn.textContent = 'Next';
        nextBtn.id = 'cutdacord-search-next';
        nextBtn.addEventListener('click', function () {
            var totalPages = Math.ceil(_searchTotal / 20);
            if (_searchPage < totalPages) {
                _searchPage++;
                performSearch(_searchQuery, _searchPage);
            }
        });

        nav.appendChild(prevBtn);
        nav.appendChild(pageInfo);
        nav.appendChild(nextBtn);
        panel.appendChild(nav);

        overlay.appendChild(panel);
        document.body.appendChild(overlay);

        // Focus input
        setTimeout(function () { input.focus(); }, 100);

        // Debounced search on input
        var debounceTimer = null;
        input.addEventListener('input', function () {
            clearTimeout(debounceTimer);
            var query = input.value.trim();
            if (query.length < 2) {
                grid.textContent = '';
                nav.style.display = 'none';
                return;
            }
            debounceTimer = setTimeout(function () {
                _searchPage = 1;
                _searchQuery = query;
                performSearch(query, 1);
            }, 400);
        });

        // Escape key
        overlay._keyHandler = function (e) {
            if (e.key === 'Escape') closeSearchModal();
        };
        document.addEventListener('keydown', overlay._keyHandler);
    }

    function closeSearchModal() {
        var overlay = document.querySelector('.cutdacord-search-overlay');
        if (overlay) {
            if (overlay._keyHandler) {
                document.removeEventListener('keydown', overlay._keyHandler);
            }
            overlay.parentNode.removeChild(overlay);
        }
    }

    function performSearch(query, page) {
        var grid = document.getElementById('cutdacord-search-grid');
        var nav = document.getElementById('cutdacord-search-nav');
        if (!grid) return;

        grid.textContent = '';
        var loading = document.createElement('div');
        loading.className = 'cutdacord-search-loading';
        loading.textContent = 'Searching...';
        grid.appendChild(loading);

        api('GET', '/v1/tmdb/search?query=' + encodeURIComponent(query) + '&page=' + page).then(function (data) {
            grid.textContent = '';

            if (!data || !data.results || data.results.length === 0) {
                var empty = document.createElement('div');
                empty.className = 'cutdacord-search-empty';
                empty.textContent = 'No results found.';
                grid.appendChild(empty);
                nav.style.display = 'none';
                return;
            }

            _searchTotal = data.total_results || data.results.length;

            for (var i = 0; i < data.results.length; i++) {
                var card = buildSearchCard(data.results[i]);
                grid.appendChild(card);
            }

            // Update nav
            var totalPages = Math.ceil(_searchTotal / 20);
            if (totalPages > 1) {
                nav.style.display = 'flex';
                var pageInfo = document.getElementById('cutdacord-search-page-info');
                if (pageInfo) pageInfo.textContent = 'Page ' + page + ' of ' + totalPages;
                var prevBtn = document.getElementById('cutdacord-search-prev');
                var nextBtn = document.getElementById('cutdacord-search-next');
                if (prevBtn) prevBtn.disabled = page <= 1;
                if (nextBtn) nextBtn.disabled = page >= totalPages;
            } else {
                nav.style.display = 'none';
            }
        });
    }

    function buildSearchCard(result) {
        var mediaType = result.media_type || (result.title ? 'movie' : 'tv');
        var title = result.title || result.name || 'Unknown';
        var year = (result.release_date || result.first_air_date || '').substring(0, 4);
        var overview = result.overview || '';
        var posterPath = result.poster_path || '';
        var tmdbId = result.id;

        var card = document.createElement('div');
        card.className = 'cutdacord-search-card';
        card.addEventListener('click', function () {
            if (mediaType === 'movie') {
                openTmdbRequestModal(tmdbId, mediaType, title, year, overview, posterPath);
            } else {
                toggleTvExpansion(card, tmdbId, title, year);
            }
        });

        // Poster
        var posterDiv = document.createElement('div');
        posterDiv.className = 'cutdacord-search-card-poster';
        if (posterPath) {
            var img = document.createElement('img');
            img.src = TMDB_IMG + '/w185' + posterPath;
            img.alt = '';
            img.loading = 'lazy';
            posterDiv.appendChild(img);
        } else {
            var noImg = document.createElement('span');
            noImg.className = 'material-icons';
            noImg.textContent = 'image';
            noImg.style.fontSize = '48px';
            noImg.style.color = 'rgba(255,255,255,0.2)';
            posterDiv.appendChild(noImg);
        }
        card.appendChild(posterDiv);

        // Badge
        var badge = document.createElement('span');
        badge.className = 'cutdacord-search-card-badge';
        badge.textContent = mediaType === 'movie' ? 'Movie' : 'TV';
        card.appendChild(badge);

        // Info
        var info = document.createElement('div');
        info.className = 'cutdacord-search-card-info';

        var titleEl = document.createElement('div');
        titleEl.className = 'cutdacord-search-card-title';
        titleEl.textContent = title;
        info.appendChild(titleEl);

        if (year) {
            var yearEl = document.createElement('div');
            yearEl.className = 'cutdacord-search-card-year';
            yearEl.textContent = year;
            info.appendChild(yearEl);
        }

        card.appendChild(info);
        return card;
    }

    function toggleTvExpansion(card, tmdbId, title, year) {
        // If already expanded, collapse
        var existing = card.parentNode.querySelector('.cutdacord-tv-expand[data-tmdb="' + tmdbId + '"]');
        if (existing) {
            existing.parentNode.removeChild(existing);
            return;
        }

        var container = document.createElement('div');
        container.className = 'cutdacord-tv-expand';
        container.setAttribute('data-tmdb', tmdbId);
        container.addEventListener('click', function(e) { e.stopPropagation(); });

        var loadingEl = document.createElement('div');
        loadingEl.className = 'cutdacord-loading';
        loadingEl.textContent = 'Loading seasons...';
        container.appendChild(loadingEl);

        // Insert after the card
        card.parentNode.insertBefore(container, card.nextSibling);

        api('GET', '/v1/tmdb/tv/' + encodeURIComponent(tmdbId) + '/seasons').then(function (data) {
            while (container.firstChild) container.removeChild(container.firstChild);

            if (!data || !data.seasons || data.seasons.length === 0) {
                var noData = document.createElement('p');
                noData.textContent = 'No season info available';
                noData.style.color = 'rgba(255,255,255,0.5)';
                noData.style.padding = '8px';
                container.appendChild(noData);
                return;
            }

            // Title bar
            var titleBar = document.createElement('div');
            titleBar.style.cssText = 'padding:8px 12px;font-weight:600;font-size:14px;border-bottom:1px solid rgba(255,255,255,0.1)';
            titleBar.textContent = title + (year ? ' (' + year + ')' : '');
            container.appendChild(titleBar);

            data.seasons.forEach(function (season) {
                var seasonNum = season.season_number;
                if (seasonNum === 0) return; // skip specials

                var header = document.createElement('div');
                header.className = 'cutdacord-season-header';

                var arrow = document.createElement('span');
                arrow.className = 'cutdacord-season-arrow';
                arrow.textContent = '\u25B6'; // right arrow
                header.appendChild(arrow);

                var label = document.createElement('span');
                label.textContent = (season.name || 'Season ' + seasonNum) + ' (' + (season.episode_count || '?') + ' episodes)';
                header.appendChild(label);

                // Full season request button
                var seasonBtn = document.createElement('button');
                seasonBtn.className = 'cutdacord-episode-request-btn';
                seasonBtn.textContent = 'Request Season';
                seasonBtn.style.marginLeft = 'auto';
                seasonBtn.addEventListener('click', function (e) {
                    e.stopPropagation();
                    seasonBtn.disabled = true;
                    seasonBtn.textContent = 'Requesting...';
                    api('POST', '/v1/request/batch', {
                        tmdb_id: parseInt(tmdbId, 10),
                        query: title,
                        seasons: [seasonNum],
                        acquisition_mode: 'download'
                    }).then(function (result) {
                        if (result) {
                            showToast('Season ' + seasonNum + ' requested!', 'success');
                            seasonBtn.textContent = 'Requested!';
                        } else {
                            showToast('Request failed', 'error');
                            seasonBtn.disabled = false;
                            seasonBtn.textContent = 'Request Season';
                        }
                    });
                });
                header.appendChild(seasonBtn);

                container.appendChild(header);

                // Episode container (hidden initially)
                var epContainer = document.createElement('div');
                epContainer.className = 'cutdacord-episode-list';
                epContainer.style.display = 'none';
                container.appendChild(epContainer);

                header.addEventListener('click', function (e) {
                    e.stopPropagation();
                    var isOpen = epContainer.style.display !== 'none';
                    if (isOpen) {
                        epContainer.style.display = 'none';
                        arrow.textContent = '\u25B6';
                        header.classList.remove('cutdacord-season-expanded');
                    } else {
                        epContainer.style.display = 'block';
                        arrow.textContent = '\u25BC';
                        header.classList.add('cutdacord-season-expanded');
                        if (!epContainer.dataset.loaded) {
                            loadEpisodes(epContainer, tmdbId, seasonNum, title);
                        }
                    }
                });
            });
        });
    }

    function loadEpisodes(container, tmdbId, seasonNum, title) {
        container.dataset.loaded = 'true';
        var loading = document.createElement('div');
        loading.className = 'cutdacord-loading';
        loading.textContent = 'Loading episodes...';
        container.appendChild(loading);

        api('GET', '/v1/tmdb/tv/' + encodeURIComponent(tmdbId) + '/season/' + seasonNum).then(function (data) {
            while (container.firstChild) container.removeChild(container.firstChild);

            if (!data || !data.episodes || data.episodes.length === 0) {
                var noEp = document.createElement('p');
                noEp.textContent = 'No episodes found';
                noEp.style.cssText = 'color:rgba(255,255,255,0.5);padding:8px 12px;font-size:13px';
                container.appendChild(noEp);
                return;
            }

            data.episodes.forEach(function (ep) {
                var row = document.createElement('div');
                row.className = 'cutdacord-episode-row';

                var info = document.createElement('div');
                info.className = 'cutdacord-episode-info';

                var epNum = document.createElement('span');
                epNum.className = 'cutdacord-episode-num';
                epNum.textContent = 'E' + (ep.episode_number < 10 ? '0' : '') + ep.episode_number;
                info.appendChild(epNum);

                var epTitle = document.createElement('span');
                epTitle.className = 'cutdacord-episode-title';
                epTitle.textContent = ep.name || 'Episode ' + ep.episode_number;
                info.appendChild(epTitle);

                row.appendChild(info);

                var reqBtn = document.createElement('button');
                reqBtn.className = 'cutdacord-episode-request-btn';
                reqBtn.textContent = 'Request';
                reqBtn.addEventListener('click', function (e) {
                    e.stopPropagation();
                    reqBtn.disabled = true;
                    reqBtn.textContent = 'Requesting...';
                    api('POST', '/v1/request', {
                        tmdb_id: parseInt(tmdbId, 10),
                        media_type: 'tv',
                        query: title,
                        season: seasonNum,
                        episode: ep.episode_number,
                        acquisition_mode: 'download'
                    }).then(function (result) {
                        if (result) {
                            showToast('S' + (seasonNum < 10 ? '0' : '') + seasonNum + 'E' + (ep.episode_number < 10 ? '0' : '') + ep.episode_number + ' requested!', 'success');
                            reqBtn.textContent = 'Requested!';
                        } else {
                            showToast('Request failed', 'error');
                            reqBtn.disabled = false;
                            reqBtn.textContent = 'Request';
                        }
                    });
                });
                row.appendChild(reqBtn);
                container.appendChild(row);
            });
        });
    }

    function openTmdbRequestModal(tmdbId, mediaType, title, year, overview, posterPath) {
        closeSearchModal();

        var fakeItem = {
            Name: title,
            ProductionYear: year || null,
            Overview: overview || null,
            Id: null,
            _tmdbPoster: posterPath || null
        };

        openRequestModal(fakeItem, String(tmdbId), mediaType);
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

        // Inject search button in header
        injectSearchButton();

        // Re-inject search button on SPA navigation (header may re-render)
        var _navDebounce = null;
        function onNavForSearch() {
            clearTimeout(_navDebounce);
            _navDebounce = setTimeout(function () {
                if (!document.querySelector('.cutdacord-search-btn')) {
                    injectSearchButton();
                }
            }, 500);
        }
        window.addEventListener('hashchange', onNavForSearch);
        window.addEventListener('popstate', onNavForSearch);

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

    /* ------------------------------------------------------------------ */
    /*  Netflix Homepage — Hero Banner + Recommendation Rows               */
    /* ------------------------------------------------------------------ */

    var _jellyfinBase = '';

    function getJellyfinBase() {
        if (_jellyfinBase) return _jellyfinBase;
        // Derive from current page URL (works for both direct and proxied access)
        _jellyfinBase = window.location.origin;
        return _jellyfinBase;
    }

    function isHomePage() {
        var hash = window.location.hash || '';
        return hash === '' || hash === '#' || hash.indexOf('#!/home') === 0 || hash === '#!/home.html';
    }

    function initHeroBanner(container) {
        if (document.querySelector('.cutdacord-hero')) return; // already rendered

        api('GET', '/v1/recommendations/featured').then(function (data) {
            if (!data || !data.id) return;

            var hero = document.createElement('div');
            hero.className = 'cutdacord-hero';

            // Background image
            var bg = document.createElement('div');
            bg.className = 'cutdacord-hero-bg';
            var jellyfinBase = (ApiClient && ApiClient._serverAddress) ? ApiClient._serverAddress : '';
            var imgUrl = jellyfinBase + '/Items/' + encodeURIComponent(data.id) + '/Images/Backdrop?maxWidth=1920&quality=80';
            if (data.backdropImageTag) {
                imgUrl += '&tag=' + encodeURIComponent(data.backdropImageTag);
            }
            bg.style.backgroundImage = 'url(' + imgUrl + ')';
            hero.appendChild(bg);

            // Gradient overlay
            var gradient = document.createElement('div');
            gradient.className = 'cutdacord-hero-gradient';
            hero.appendChild(gradient);

            // Content
            var content = document.createElement('div');
            content.className = 'cutdacord-hero-content';

            var title = document.createElement('h1');
            title.className = 'cutdacord-hero-title';
            title.textContent = data.name;
            content.appendChild(title);

            // Meta line
            var metaParts = [];
            if (data.year) metaParts.push(data.year);
            if (data.rating) metaParts.push(data.rating);
            if (data.communityRating) metaParts.push('\u2605 ' + data.communityRating.toFixed(1));
            if (data.genres && data.genres.length > 0) metaParts.push(data.genres.slice(0, 3).join(', '));
            if (metaParts.length > 0) {
                var meta = document.createElement('p');
                meta.className = 'cutdacord-hero-meta';
                meta.textContent = metaParts.join(' \u00B7 ');
                content.appendChild(meta);
            }

            // Overview
            if (data.overview) {
                var overview = document.createElement('p');
                overview.className = 'cutdacord-hero-overview';
                overview.textContent = data.overview;
                content.appendChild(overview);
            }

            // Action buttons
            var actions = document.createElement('div');
            actions.className = 'cutdacord-hero-actions';

            var playBtn = document.createElement('button');
            playBtn.className = 'cutdacord-hero-btn cutdacord-hero-btn--play';
            playBtn.textContent = '\u25B6 Play';
            playBtn.addEventListener('click', function () {
                window.location.hash = '#!/details?id=' + encodeURIComponent(data.id) + '&autoplay=true';
            });
            actions.appendChild(playBtn);

            var infoBtn = document.createElement('button');
            infoBtn.className = 'cutdacord-hero-btn cutdacord-hero-btn--info';
            infoBtn.textContent = '\u2139 More Info';
            infoBtn.addEventListener('click', function () {
                window.location.hash = '#!/details?id=' + encodeURIComponent(data.id);
            });
            actions.appendChild(infoBtn);

            content.appendChild(actions);
            hero.appendChild(content);

            // Insert at top of homepage sections
            container.insertBefore(hero, container.firstChild);
        }).catch(function (err) {
            console.warn('[CutDaCord] Hero banner unavailable:', err);
        });
    }

    function initRecommendationRows(container) {
        // Don't add twice
        if (container.querySelector('.cutdacord-rec-section')) return;

        api('GET', '/v1/recommendations?limit=3').then(function (data) {
            if (!data || !data.sections || data.sections.length === 0) return;

            // Find insertion point: after the 2nd existing section (or at end)
            var existingSections = container.querySelectorAll('.verticalSection');
            var insertBefore = existingSections.length > 2 ? existingSections[2] : null;

            data.sections.forEach(function (section) {
                var sectionEl = document.createElement('div');
                sectionEl.className = 'cutdacord-rec-section';

                var titleEl = document.createElement('h2');
                titleEl.className = 'cutdacord-rec-title';
                var reasonSpan = document.createElement('span');
                reasonSpan.className = 'cutdacord-rec-reason';
                reasonSpan.textContent = 'Because You Watched ';
                titleEl.appendChild(reasonSpan);
                titleEl.appendChild(document.createTextNode(section.basedOn));
                sectionEl.appendChild(titleEl);

                var scroller = document.createElement('div');
                scroller.className = 'cutdacord-rec-scroller';

                section.items.forEach(function (item) {
                    var card = document.createElement('a');
                    card.className = 'cutdacord-rec-card';
                    card.href = '#!/details?id=' + encodeURIComponent(item.id);

                    var img = document.createElement('img');
                    img.className = 'cutdacord-rec-card-img';
                    img.alt = item.name || '';
                    img.loading = 'lazy';
                    var posterUrl = getJellyfinBase() + '/Items/' + encodeURIComponent(item.id) + '/Images/Primary?maxWidth=200&quality=80';
                    if (item.primaryImageTag) {
                        posterUrl += '&tag=' + encodeURIComponent(item.primaryImageTag);
                    }
                    var safePoster = sanitizeImageUrl(posterUrl, [getJellyfinBase()]);
                    if (safePoster) {
                        img.src = safePoster;
                    }
                    card.appendChild(img);

                    var cardTitle = document.createElement('div');
                    cardTitle.className = 'cutdacord-rec-card-title';
                    cardTitle.textContent = item.name || 'Unknown';
                    card.appendChild(cardTitle);

                    scroller.appendChild(card);
                });

                sectionEl.appendChild(scroller);

                if (insertBefore) {
                    container.insertBefore(sectionEl, insertBefore);
                } else {
                    container.appendChild(sectionEl);
                }
            });
        }).catch(function (err) {
            console.warn('[CutDaCord] Recommendation rows error:', err);
        });
    }

    function initNetflixHomepage() {
        if (!isHomePage()) return;

        var container = document.querySelector('.homeSectionsContainer');
        if (container) {
            initHeroBanner(container);
            initRecommendationRows(container);
            return;
        }

        // MutationObserver to detect container appearance
        var observer = new MutationObserver(function () {
            var found = document.querySelector('.homeSectionsContainer');
            if (found) {
                observer.disconnect();
                initHeroBanner(found);
                initRecommendationRows(found);
            }
        });
        observer.observe(document.body, { childList: true, subtree: true });

        // Safety timeout: disconnect observer after 15s
        setTimeout(function () { observer.disconnect(); }, 15000);
    }

    // Listen for SPA navigation
    window.addEventListener('hashchange', function () {
        if (!isHomePage()) {
            // Clean up Netflix elements when navigating away
            var existingHero = document.querySelector('.cutdacord-hero');
            if (existingHero) existingHero.remove();
            document.querySelectorAll('.cutdacord-rec-section').forEach(function (el) { el.remove(); });
        } else {
            // Small delay to let Jellyfin render the new page
            setTimeout(initNetflixHomepage, 500);
        }
    });

    // Initial call
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initNetflixHomepage);
    } else {
        initNetflixHomepage();
    }

})();
