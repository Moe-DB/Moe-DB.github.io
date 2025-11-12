window.addEventListener('DOMContentLoaded', function () {
    fetch('./anilist_data_with_img_status.csv')
        .then(r => r.text())
        .then(csvText => {
            const rows = csvText.split(/\r?\n/).filter(Boolean);
            if(rows.length < 2) return;
            const headers = rows[0].split(',');

            function parseRow(row) {
                const result = [];
                let inQuote = false;
                let currentField = '';
                for (let i = 0; i < row.length; i++) {
                    const char = row[i];
                    if (char === '"') {
                        if (inQuote && i + 1 < row.length && row[i + 1] === '"') {
                            currentField += '"';
                            i++;
                        } else {
                            inQuote = !inQuote;
                        }
                    } else if (char === ',') {
                        if (inQuote) {
                            currentField += char;
                        } else {
                            result.push(currentField.trim());
                            currentField = '';
                        }
                    } else {
                        currentField += char;
                    }
                }
                result.push(currentField.trim());
                return result;
            }

            const data = rows.slice(1).map(row => {
                const cols = parseRow(row);
                const obj = {};
                headers.forEach((h, i) => obj[h.trim()] = cols[i]||'');
                return obj;
            });

            // Removed partitioning into withImg and withoutImg
            window.all_media = data;
            // window.media_partitioned = { withImg, withoutImg }; // No longer needed
            window.current_display_media = [...data]; // Initialize with all data

            renderPage();

            document.getElementById('search-input').addEventListener('input', handleSearch);
            document.getElementById('titles-per-row-select').addEventListener('change', updateGridLayout);
            updateGridLayout();
            initFilters(data);

            document.getElementById('toggle-img-btn').addEventListener('change', () => {
                applyFilters();
            });

            const sortBySelect = document.getElementById('sort-by-select');
            const sortDirectionBtn = document.getElementById('sort-direction-btn');
            sortBySelect.addEventListener('change', () => sortMedia(sortBySelect.value, sortDirectionBtn.dataset.direction));
            sortDirectionBtn.addEventListener('click', () => {
                const currentDirection = sortDirectionBtn.dataset.direction;
                const newDirection = currentDirection === 'asc' ? 'desc' : 'asc';
                sortDirectionBtn.dataset.direction = newDirection;
                sortDirectionBtn.textContent = newDirection === 'asc' ? '▲' : '▼';
                sortMedia(sortBySelect.value, newDirection);
            });

            window.currentSort = { key: 'Vocab Density (%)', direction: 'asc' };
            sortMedia(window.currentSort.key, window.currentSort.direction);

            document.getElementById('prev-page-btn').addEventListener('click', () => changePage('prev'));
            document.getElementById('next-page-btn').addEventListener('click', () => changePage('next'));
            document.getElementById('prev-page-btn-bottom').addEventListener('click', () => changePage('prev'));
            document.getElementById('next-page-btn-bottom').addEventListener('click', () => changePage('next'));
        })
        .catch(err => {
            document.getElementById('media-list').innerHTML = '<div style="color:#ff6b6b; padding:40px; text-align:center; font-size:1.1em;">Could not load the CSV file. Please ensure the file is in the project folder and you are running a web server.</div>';
        });
});

const activeFilters = {};
window.currentPage = 1;
window.itemsPerPage = 50;
window.totalPages = 1;

function initFilters(data) {
    const genres = new Set();
    const statuses = new Set();
    const entryTypes = new Set();
    let minEpisodes = Infinity, maxEpisodes = 0;
    let minYear = Infinity, maxYear = 0;
    let minScore = Infinity, maxScore = 0;
    let minVocabDensity = Infinity, maxVocabDensity = 0;
    let minKanjiDifficulty = Infinity, maxKanjiDifficulty = 0;
    let minVocabDifficulty = Infinity, maxVocabDifficulty = 0;
    let minOverallDifficulty = Infinity, maxOverallDifficulty = 0;
    let minAvgWords = Infinity, maxAvgWords = 0;
    let minUniqueWords = Infinity, maxUniqueWords = 0;

    data.forEach(item => {
        if (item.genres) {
            item.genres.split(', ').forEach(genre => genres.add(genre.trim()));
        }
        if (item.status) statuses.add(item.status.trim());
        if (item.entry_type) entryTypes.add(item.entry_type.trim());

        const safeParseFloat = (val) => isNaN(parseFloat(val)) ? undefined : parseFloat(val);

        const episodes = safeParseFloat(item.episodes);
        if (episodes !== undefined) {
            minEpisodes = Math.min(minEpisodes, episodes);
            maxEpisodes = Math.max(maxEpisodes, episodes);
        }

        const year = safeParseFloat(item.start_year);
        if (year !== undefined) {
            minYear = Math.min(minYear, year);
            maxYear = Math.max(maxYear, year);
        }

        const score = safeParseFloat(item.average_score);
        if (score !== undefined) {
            minScore = Math.min(minScore, score);
            maxScore = Math.max(maxScore, score);
        }

        const vocabDensity = safeParseFloat(item['Vocab Density (%)']);
        if (vocabDensity !== undefined) {
            minVocabDensity = Math.min(minVocabDensity, vocabDensity);
            maxVocabDensity = Math.max(maxVocabDensity, vocabDensity);
        }

        const kanjiDifficulty = safeParseFloat(item['Kanji Difficulty (1-100)']);
        if (kanjiDifficulty !== undefined) {
            minKanjiDifficulty = Math.min(minKanjiDifficulty, kanjiDifficulty);
            maxKanjiDifficulty = Math.max(maxKanjiDifficulty, kanjiDifficulty);
        }

        const vocabDifficulty = safeParseFloat(item['Vocab Difficulty (1-100)']);
        if (vocabDifficulty !== undefined) {
            minVocabDifficulty = Math.min(minVocabDifficulty, vocabDifficulty);
            maxVocabDifficulty = Math.max(maxVocabDifficulty, vocabDifficulty);
        }

        const overallDifficulty = safeParseFloat(item['Overall Difficulty (1-100)']);
        if (overallDifficulty !== undefined) {
            minOverallDifficulty = Math.min(minOverallDifficulty, overallDifficulty);
            maxOverallDifficulty = Math.max(maxOverallDifficulty, overallDifficulty);
        }

        const avgWords = safeParseFloat(item['Avg. Words/Episode']);
        if (avgWords !== undefined) {
            minAvgWords = Math.min(minAvgWords, avgWords);
            maxAvgWords = Math.max(maxAvgWords, avgWords);
        }

        const uniqueWords = safeParseFloat(item['Unique Words']);
        if (uniqueWords !== undefined) {
            minUniqueWords = Math.min(minUniqueWords, uniqueWords);
            maxUniqueWords = Math.max(maxUniqueWords, uniqueWords);
        }
    });

    renderSlider('unique-words-filter', minUniqueWords, maxUniqueWords, 'unique_words');

    // Render all filter sections in desired order
    // 1. Entry Type
    renderCheckboxes('entry-type-filter', [...entryTypes].sort().map(type => ({
        value: type,
        display: type === 'anime_movie' ? 'Anime Movie' :
                 type === 'anime_tv' ? 'Anime TV' :
                 type === 'drama_movie' ? 'Drama Movie' :
                 type === 'drama_tv' ? 'Drama TV' :
                 type
    })), 'entry_type');
    
    // 2. Genres (foldable)
    renderFoldableCheckboxes('genres-filter', [...genres].sort(), 'genres', 4);
    
    // 3. Status
    renderCheckboxes('status-filter', [...statuses].sort().map(status => ({
        value: status,
        display: status
    })), 'status');

    // 4. Sliders
    renderSlider('episodes-filter', minEpisodes, maxEpisodes, 'episodes');
    renderSlider('year-filter', minYear, maxYear, 'year');
    renderSlider('score-filter', minScore, maxScore, 'score');
    renderSlider('vocab-density-filter', minVocabDensity, maxVocabDensity, 'vocab_density');
    renderSlider('kanji-difficulty-filter', minKanjiDifficulty, maxKanjiDifficulty, 'kanji_difficulty');
    renderSlider('vocab-difficulty-filter', minVocabDifficulty, maxVocabDifficulty, 'vocab_difficulty');
    renderSlider('overall-difficulty-filter', minOverallDifficulty, maxOverallDifficulty, 'overall_difficulty');
    renderSlider('avg-words-episode-filter', minAvgWords, maxAvgWords, 'avg_words_episode');
    renderSlider('unique-words-filter', minUniqueWords, maxUniqueWords, 'unique_words');

    document.querySelectorAll('.filter-checkbox input').forEach(checkbox => {
        checkbox.addEventListener('change', applyFilters);
    });
    document.querySelectorAll('.filter-slider input').forEach(slider => {
        slider.addEventListener('change', applyFilters);
    });
}

function renderCheckboxes(containerId, values, filterKey) {
    const container = document.getElementById(containerId);
    container.innerHTML = ''; // Clear previous content to prevent duplicates on re-render
    values.forEach(item => {
        const label = document.createElement('label');
        label.className = 'filter-checkbox';
        label.innerHTML = `
            <input type="checkbox" value="${item.value}" data-filter-key="${filterKey}">
            ${item.display}
        `;
        container.appendChild(label);
    });
}

function renderFoldableCheckboxes(containerId, values, filterKey, limit) {
    const container = document.getElementById(containerId);
    container.innerHTML = ''; // Clear previous content

    const visibleValues = values.slice(0, limit);
    const hiddenValues = values.slice(limit);

    visibleValues.forEach(value => {
        const label = document.createElement('label');
        label.className = 'filter-checkbox';
        label.innerHTML = `
            <input type="checkbox" value="${value}" data-filter-key="${filterKey}">
            ${value}
        `;
        container.appendChild(label);
    });

    if (hiddenValues.length > 0) {
        const hiddenContainer = document.createElement('div');
        hiddenContainer.className = 'hidden-checkboxes';
        hiddenContainer.style.display = 'none'; // Initially hidden

        hiddenValues.forEach(value => {
            const label = document.createElement('label');
            label.className = 'filter-checkbox';
            label.innerHTML = `
                <input type="checkbox" value="${value}" data-filter-key="${filterKey}">
                ${value}
            `;
            hiddenContainer.appendChild(label);
        });
        container.appendChild(hiddenContainer);

        const showMoreBtn = document.createElement('button');
        showMoreBtn.className = 'show-more-btn';
        showMoreBtn.textContent = hiddenContainer.style.display === 'none' ? `Show ${hiddenValues.length} More` : 'Show Less';
        // Apply inline styles to make it look like a link
        showMoreBtn.style.background = 'none';
        showMoreBtn.style.border = 'none';
        showMoreBtn.style.color = '#007bff'; // A common link color
        showMoreBtn.style.cursor = 'pointer';
        showMoreBtn.style.textDecoration = 'underline';
        showMoreBtn.style.padding = '0';
        showMoreBtn.style.font = 'inherit';
        showMoreBtn.addEventListener('click', (event) => {
            event.preventDefault(); // Prevent default button behavior
            hiddenContainer.style.display = hiddenContainer.style.display === 'none' ? 'block' : 'none';
            showMoreBtn.textContent = hiddenContainer.style.display === 'none' ? `Show ${hiddenValues.length} More` : 'Show Less';
        });
        container.appendChild(showMoreBtn);
    }
}

function renderSlider(containerId, min, max, filterKey) {
    const container = document.getElementById(containerId);
    container.className = 'filter-slider';
    container.innerHTML = `
        <label for="${filterKey}-min">Min:</label>
        <input type="range" id="${filterKey}-min" min="${Math.floor(min)}" max="${Math.ceil(max)}" value="${Math.floor(min)}" data-filter-key="${filterKey}" data-filter-type="min">
        <span id="${filterKey}-min-val">${Math.floor(min)}</span>
        <br>
        <label for="${filterKey}-max">Max:</label>
        <input type="range" id="${filterKey}-max" min="${Math.floor(min)}" max="${Math.ceil(max)}" value="${Math.ceil(max)}" data-filter-key="${filterKey}" data-filter-type="max">
        <span id="${filterKey}-max-val">${Math.ceil(max)}</span>
    `;
    const minSlider = container.querySelector(`#${filterKey}-min`);
    const maxSlider = container.querySelector(`#${filterKey}-max`);
    const minValSpan = container.querySelector(`#${filterKey}-min-val`);
    const maxValSpan = container.querySelector(`#${filterKey}-max-val`);

    minSlider.addEventListener('input', (e) => {
        minValSpan.textContent = e.target.value;
        if (parseFloat(minSlider.value) > parseFloat(maxSlider.value)) {
            maxSlider.value = minSlider.value;
            maxValSpan.textContent = minSlider.value;
        }
    });

    maxSlider.addEventListener('input', (e) => {
        maxValSpan.textContent = e.target.value;
        if (parseFloat(maxSlider.value) < parseFloat(minSlider.value)) {
            minSlider.value = maxSlider.value;
            minValSpan.textContent = maxSlider.value;
        }
    });

    activeFilters[filterKey] = { min: Math.floor(min), max: Math.ceil(max) };
}

function applyFilters() {
    const searchTerm = document.getElementById('search-input').value.toLowerCase().trim();
    const currentFilters = {};

    document.querySelectorAll('.filter-checkbox input:checked').forEach(checkbox => {
        const key = checkbox.dataset.filterKey;
        if (!currentFilters[key]) currentFilters[key] = new Set();
        currentFilters[key].add(checkbox.value);
    });

    document.querySelectorAll('.filter-slider input[type="range"]').forEach(slider => {
        const key = slider.dataset.filterKey;
        const type = slider.dataset.filterType;
        if (!currentFilters[key]) currentFilters[key] = { min: -Infinity, max: Infinity };
        if (type === 'min') currentFilters[key].min = parseFloat(slider.value);
        if (type === 'max') currentFilters[key].max = parseFloat(slider.value);
    });

    const filteredMedia = window.all_media.filter(item => {
        let matchesAllFilters = true;

        if (searchTerm) {
            const itemTitle = item['Anime Title'] ? item['Anime Title'].toLowerCase() : '';
            const itemEnglishName = item['english_name'] ? item['english_name'].toLowerCase() : '';
            const itemJapaneseName = item['japanese_name'] ? item['japanese_name'].toLowerCase() : '';
            const searchMatch = itemTitle.includes(searchTerm) || 
                                itemEnglishName.includes(searchTerm) || 
                                itemJapaneseName.includes(searchTerm);
            if (!searchMatch) matchesAllFilters = false;
        }

        for (const key in currentFilters) {
            const filterValue = currentFilters[key];
            let itemValue;

            switch (key) {
                case 'genres':
                    itemValue = item.genres ? item.genres.split(', ').map(g => g.trim()) : [];
                    if (filterValue.size > 0 && !itemValue.some(g => filterValue.has(g))) matchesAllFilters = false;
                    break;
                case 'status':
                    itemValue = item.status ? item.status.trim() : '';
                    if (filterValue.size > 0 && !filterValue.has(itemValue)) matchesAllFilters = false;
                    break;
                case 'entry_type':
                    itemValue = item.entry_type ? item.entry_type.trim() : '';
                    if (filterValue.size > 0 && !filterValue.has(itemValue)) matchesAllFilters = false;
                    break;
                case 'episodes':
                    itemValue = parseFloat(item.episodes);
                    if (itemValue < filterValue.min || itemValue > filterValue.max) matchesAllFilters = false;
                    break;
                case 'year':
                    itemValue = parseFloat(item.start_year);
                    if (itemValue < filterValue.min || itemValue > filterValue.max) matchesAllFilters = false;
                    break;
                case 'score':
                    itemValue = parseFloat(item.average_score);
                    if (itemValue < filterValue.min || itemValue > filterValue.max) matchesAllFilters = false;
                    break;
                case 'vocab_density':
                    itemValue = parseFloat(item['Vocab Density (%)']);
                    if (itemValue < filterValue.min || itemValue > filterValue.max) matchesAllFilters = false;
                    break;
                case 'kanji_difficulty':
                    itemValue = parseFloat(item['Kanji Difficulty (1-100)']);
                    if (itemValue < filterValue.min || itemValue > filterValue.max) matchesAllFilters = false;
                    break;
                case 'vocab_difficulty':
                    itemValue = parseFloat(item['Vocab Difficulty (1-100)']);
                    if (itemValue < filterValue.min || itemValue > filterValue.max) matchesAllFilters = false;
                    break;
                case 'overall_difficulty':
                    itemValue = parseFloat(item['Overall Difficulty (1-100)']);
                    if (itemValue < filterValue.min || itemValue > filterValue.max) matchesAllFilters = false;
                    break;
                case 'avg_words_episode':
                    itemValue = parseFloat(item['Avg. Words/Episode']);
                    if (itemValue < filterValue.min || itemValue > filterValue.max) matchesAllFilters = false;
                    break;
                case 'unique_words':
                    itemValue = parseFloat(item['Unique Words']);
                    if (itemValue < filterValue.min || itemValue > filterValue.max) matchesAllFilters = false;
                    break;
            }
            if (!matchesAllFilters) return false;
        }

        // Filter for entries without images if the toggle checkbox is checked
        const toggleImgBtn = document.getElementById('toggle-img-btn');
        if (toggleImgBtn && toggleImgBtn.checked) {
            const hasAnilistImg = item.anilist_img_filename && item.anilist_img_filename.trim() !== '';
            const hasTmdbImg = item.tmdb_img_filename && item.tmdb_img_filename.trim() !== '';
            if (!hasAnilistImg && !hasTmdbImg) {
                matchesAllFilters = false;
            }
        }

        return matchesAllFilters;
    });

    // Removed partitioning into filteredWithImg and filteredWithoutImg
    window.current_display_media = filteredMedia;
    window.currentPage = 1;
    renderPage();
}

function sortMedia(sortBy, sortDirection) {
    window.currentSort.key = sortBy;
    window.currentSort.direction = sortDirection;

    const sortKeyMap = {
        'vocab_density': 'Vocab Density (%)',
        'overall_difficulty': 'Overall Difficulty (1-100)',
        'kanji_difficulty': 'Kanji Difficulty (1-100)',
        'vocab_difficulty': 'Vocab Difficulty (1-100)',
        'avg_words_episode': 'Avg. Words/Episode',
        'unique_words': 'Unique Words',
        'score': 'average_score',
        'year': 'start_year',
        'episodes': 'episodes',
        'Anime Title': 'Anime Title',
        'english_name': 'english_name',
        'japanese_name': 'japanese_name'
    };

    const actualSortKey = sortKeyMap[sortBy] || sortBy; // Use mapped key or fallback to original

    const parseValue = (item, key) => {
        if (['Anime Title', 'english_name', 'japanese_name', 'genres', 'status', 'entry_type'].includes(key)) {
            return (item[key] || '').toLowerCase();
        } else {
            const value = parseFloat(item[key]);
            return isNaN(value) ? (sortDirection === 'asc' ? Infinity : -Infinity) : value;
        }
    };

    window.all_media.sort((a, b) => {
        let valA = parseValue(a, actualSortKey); // Use actualSortKey here
        let valB = parseValue(b, actualSortKey); // Use actualSortKey here

        if (typeof valA === 'string' && typeof valB === 'string') {
            return sortDirection === 'asc' ? valA.localeCompare(valB) : valB.localeCompare(valA);
        } else {
            return sortDirection === 'asc' ? valA - valB : valB - valA;
        }
    });

    applyFilters();
}

function handleSearch() {
    applyFilters();
}

function renderPage() {
    // const {withImg, withoutImg} = window.current_display_media; // No longer partitioned
    const displayedMedia = window.current_display_media; // Use a single array
    const totalItems = displayedMedia.length; // Use total length of single array
    window.totalPages = Math.ceil(totalItems / window.itemsPerPage);

    document.getElementById('page-info').textContent = `Page ${window.currentPage} of ${window.totalPages}`;
    document.getElementById('page-info-bottom').textContent = `Page ${window.currentPage} of ${window.totalPages}`;
    document.getElementById('prev-page-btn').disabled = window.currentPage === 1;
    document.getElementById('next-page-btn').disabled = window.currentPage === window.totalPages;
    document.getElementById('prev-page-btn-bottom').disabled = window.currentPage === 1;
    document.getElementById('next-page-btn-bottom').disabled = window.currentPage === window.totalPages;

    const start = (window.currentPage - 1) * window.itemsPerPage;
    const end = start + window.itemsPerPage;

    document.getElementById('media-list').innerHTML = '';

    // Render all items in a single loop
    for (let i = start; i < end && i < totalItems; i++) {
        renderMediaCard(displayedMedia[i]);
    }
}

function changePage(direction) {
    if (direction === 'next' && window.currentPage < window.totalPages) {
        window.currentPage++;
    } else if (direction === 'prev' && window.currentPage > 1) {
        window.currentPage--;
    }
    renderPage();
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function updateGridLayout() {
    const titlesPerRow = document.getElementById('titles-per-row-select').value;
    const mediaList = document.getElementById('media-list');
    mediaList.style.gridTemplateColumns = `repeat(${titlesPerRow}, 1fr)`;
}

function renderMediaCard(item) {
    const list = document.getElementById('media-list');
        const card = document.createElement('div');
    card.className = 'media-card collapsed'; // Start collapsed
    
    const posterSection = document.createElement('div');
    posterSection.className = 'poster-container';
    
    let imageUrl = '';
    let imageAlt = '';

    if (item.anilist_img_filename) {
        imageUrl = 'img/anilistimg/' + item.anilist_img_filename;
        imageAlt = item['Anime Title'] || item['english_name'] || 'Poster';
    } else if (item.tmdb_img_filename) {
        imageUrl = 'img/tmdbimg/' + item.tmdb_img_filename;
        imageAlt = item['Anime Title'] || item['english_name'] || 'Poster';
    }

    // Always create an img element, use placeholder if no poster available
    const img = document.createElement('img');
    img.src = imageUrl || 'img/no_image.png';
    img.alt = imageAlt;
    img.className = 'poster';
    img.loading = 'lazy';
    posterSection.appendChild(img);
    
        card.appendChild(posterSection);

        const body = document.createElement('div');
        body.className = 'card-body';

    const cardContentWrapper = document.createElement('div');
    cardContentWrapper.className = 'card-content-wrapper';

    // Top visible content
    cardContentWrapper.innerHTML = `
            <div class="media-title">${item['Anime Title'] || ''}</div>
            <div class="media-japanese">${item['japanese_name'] || ''}</div>
    `;

    // Container for details that will fade out in collapsed state
    const fadeOutContainer = document.createElement('div');
    fadeOutContainer.className = 'fade-out-container';
    fadeOutContainer.innerHTML = `
            <div class="media-genre"><b>Genres:</b> ${item['genres'] || '-'}</div>
            <div class="details"><b>Status:</b> ${item['status'] || '-'} | <b>Episodes:</b> ${item['episodes'] || '-'}</div>
            <div class="details"><b>Year:</b> ${item['start_year'] || '-'} | <b>Score:</b> ${item['average_score'] || '-'}</div>
            <div class="details"><b>Entry Type:</b> ${item['entry_type'] || '-'}</div>
        `;
    cardContentWrapper.appendChild(fadeOutContainer);

    // Collapsible details section (only difficulty details now)
    const collapsibleDetails = document.createElement('div');
    collapsibleDetails.className = 'details-collapsible';
    collapsibleDetails.innerHTML = `
        <div class="difficulty-details">
            <b>Kanji Difficulty:</b> ${item['Kanji Difficulty (1-100)'] || '-'} &nbsp;
            <b>Vocab Difficulty:</b> ${item['Vocab Difficulty (1-100)'] || '-'} &nbsp;
            <b>Overall Difficulty:</b> ${item['Overall Difficulty (1-100)'] || '-'} <br>
            <b>Avg Words/Episode:</b> ${item['Avg. Words/Episode'] || '-'} &nbsp;
            <b>Unique Words:</b> ${item['Unique Words'] || '-'} 
        </div>
    `;
    cardContentWrapper.appendChild(collapsibleDetails);
    
    body.appendChild(cardContentWrapper); // Append the wrapper to the body

        const density = document.createElement('div');
        density.className = 'vocab-density';
        density.innerText = `Vocab Density: ${item['Vocab Density (%)'] || '--'}%`;
        body.appendChild(density);

        card.appendChild(body);
        list.appendChild(card);

    card.addEventListener('click', () => {
        card.classList.toggle('collapsed');
    });
}
