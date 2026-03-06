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
            openTmdbRequestModal(tmdbId, mediaType, title, year, overview, posterPath);
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

})();
