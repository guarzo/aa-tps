/**
 * AA Campaign Dashboard JavaScript
 * Handles chart initialization, data fetching, and UI interactions
 */

(function() {
    'use strict';

    // Configuration
    const CONFIG = {
        chartColors: {
            kills: 'rgba(40, 167, 69, 0.7)',
            killsBorder: 'rgba(40, 167, 69, 1)',
            losses: 'rgba(220, 53, 69, 0.7)',
            lossesBorder: 'rgba(220, 53, 69, 1)',
            iskDestroyed: 'rgba(40, 167, 69, 0.2)',
            iskLost: 'rgba(220, 53, 69, 0.2)',
            shipClasses: [
                '#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0',
                '#9966FF', '#FF9F40', '#C9CBCF', '#7BC043',
                '#E91E63', '#00BCD4', '#8BC34A', '#FF5722'
            ]
        },
        animationDuration: 1500,
        counterDuration: 1000
    };

    // State
    let activityChart = null;
    let shipClassChart = null;
    let leaderboardTable = null;
    let currentYear = null;
    let currentMonth = null;

    /**
     * Format ISK value for display
     * @param {number} value - The ISK value
     * @returns {string} Formatted string
     */
    function formatISK(value) {
        if (value === null || value === undefined) return '0';
        value = parseFloat(value);
        if (value >= 1e12) return (value / 1e12).toFixed(2) + 'T';
        if (value >= 1e9) return (value / 1e9).toFixed(2) + 'B';
        if (value >= 1e6) return (value / 1e6).toFixed(2) + 'M';
        if (value >= 1e3) return (value / 1e3).toFixed(2) + 'K';
        return value.toFixed(0);
    }

    /**
     * Format number with commas
     * @param {number} value - The number
     * @returns {string} Formatted string
     */
    function formatNumber(value) {
        return value.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    }

    /**
     * Animate counter from 0 to target value
     * @param {HTMLElement} element - The element to animate
     * @param {number} target - Target value
     * @param {string} format - Format type ('number', 'isk', 'percent')
     */
    function animateCounter(element, target, format = 'number') {
        if (!element) return;

        const startTime = performance.now();
        const duration = CONFIG.counterDuration;

        function update(currentTime) {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);

            // Easing function (ease-out)
            const easeProgress = 1 - Math.pow(1 - progress, 3);
            const currentValue = target * easeProgress;

            let displayValue;
            switch (format) {
                case 'isk':
                    displayValue = formatISK(currentValue);
                    break;
                case 'percent':
                    displayValue = currentValue.toFixed(1) + '%';
                    break;
                default:
                    displayValue = formatNumber(Math.round(currentValue));
            }

            element.textContent = displayValue;

            if (progress < 1) {
                requestAnimationFrame(update);
            }
        }

        requestAnimationFrame(update);
    }

    /**
     * Get API URL with optional year/month params
     * @param {string} endpoint - API endpoint name
     * @returns {string} Full URL with params
     */
    function getApiUrl(endpoint) {
        let url = window.AAC_URLS[endpoint];
        if (currentYear && currentMonth) {
            url += '?year=' + currentYear + '&month=' + currentMonth;
        }
        return url;
    }

    /**
     * Load and display stats cards
     */
    function loadStats() {
        const url = getApiUrl('stats');

        fetch(url)
            .then(response => response.json())
            .then(data => {
                // Animate stats counters
                animateCounter(document.getElementById('stat-kills'), data.total_kills);
                animateCounter(document.getElementById('stat-losses'), data.total_losses);
                animateCounter(document.getElementById('stat-isk-destroyed'), data.total_kill_value, 'isk');
                animateCounter(document.getElementById('stat-isk-lost'), data.total_loss_value, 'isk');
                animateCounter(document.getElementById('stat-efficiency'), data.efficiency, 'percent');
                animateCounter(document.getElementById('stat-pilots'), data.active_pilots);

                // Update efficiency bar
                const efficiencyBar = document.getElementById('efficiency-bar-fill');
                if (efficiencyBar) {
                    efficiencyBar.style.width = data.efficiency + '%';
                }
            })
            .catch(error => {
                console.error('Error loading stats:', error);
            });
    }

    /**
     * Initialize and load activity chart
     */
    function loadActivityChart() {
        const ctx = document.getElementById('activityChart');
        if (!ctx) return;

        const url = getApiUrl('activity');

        fetch(url)
            .then(response => response.json())
            .then(data => {
                const chartData = data.data || [];

                const labels = chartData.map(d => {
                    const date = new Date(d.day);
                    return date.getDate();
                });
                const kills = chartData.map(d => d.kills);
                const losses = chartData.map(d => d.losses);
                const killValues = chartData.map(d => d.kill_value);
                const lossValues = chartData.map(d => d.loss_value);

                if (activityChart) {
                    activityChart.destroy();
                }

                activityChart = new Chart(ctx, {
                    type: 'bar',
                    data: {
                        labels: labels,
                        datasets: [
                            {
                                label: 'Kills',
                                data: kills,
                                backgroundColor: CONFIG.chartColors.kills,
                                borderColor: CONFIG.chartColors.killsBorder,
                                borderWidth: 1
                            },
                            {
                                label: 'Losses',
                                data: losses,
                                backgroundColor: CONFIG.chartColors.losses,
                                borderColor: CONFIG.chartColors.lossesBorder,
                                borderWidth: 1
                            }
                        ]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            x: {
                                title: {
                                    display: true,
                                    text: 'Day of Month'
                                }
                            },
                            y: {
                                beginAtZero: true,
                                ticks: {
                                    stepSize: 1
                                }
                            }
                        },
                        plugins: {
                            legend: {
                                position: 'top'
                            },
                            tooltip: {
                                callbacks: {
                                    afterBody: function(context) {
                                        const index = context[0].dataIndex;
                                        const datasetIndex = context[0].datasetIndex;
                                        if (datasetIndex === 0) {
                                            return 'ISK: ' + formatISK(killValues[index]);
                                        } else {
                                            return 'ISK: ' + formatISK(lossValues[index]);
                                        }
                                    }
                                }
                            }
                        }
                    }
                });
            })
            .catch(error => {
                console.error('Error loading activity data:', error);
            });
    }

    /**
     * Initialize and load ship class chart
     */
    function loadShipClassChart() {
        const ctx = document.getElementById('shipClassChart');
        if (!ctx) return;

        const url = getApiUrl('shipStats');

        fetch(url)
            .then(response => response.json())
            .then(data => {
                const chartData = data.data || [];

                // Take top 10 ship classes
                const topClasses = chartData.slice(0, 10);
                const labels = topClasses.map(d => d.ship_group);
                const values = topClasses.map(d => d.killed);

                if (shipClassChart) {
                    shipClassChart.destroy();
                }

                shipClassChart = new Chart(ctx, {
                    type: 'doughnut',
                    data: {
                        labels: labels,
                        datasets: [{
                            data: values,
                            backgroundColor: CONFIG.chartColors.shipClasses.slice(0, labels.length)
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: {
                                position: 'right',
                                labels: {
                                    boxWidth: 12,
                                    padding: 8,
                                    font: {
                                        size: 11
                                    }
                                }
                            },
                            tooltip: {
                                callbacks: {
                                    label: function(context) {
                                        const label = context.label || '';
                                        const value = context.raw || 0;
                                        const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                        const percentage = ((value / total) * 100).toFixed(1);
                                        return label + ': ' + value + ' (' + percentage + '%)';
                                    }
                                }
                            }
                        }
                    }
                });
            })
            .catch(error => {
                console.error('Error loading ship stats:', error);
            });
    }

    /**
     * Load top kills
     */
    function loadTopKills() {
        const container = document.getElementById('top-kills-list');
        if (!container) return;

        container.innerHTML = '<div class="loading-spinner"></div>';

        const url = getApiUrl('topKills') + (currentYear ? '&' : '?') + 'limit=10';

        fetch(url)
            .then(response => response.json())
            .then(data => {
                const kills = data.data || [];

                if (kills.length === 0) {
                    container.innerHTML = `
                        <div class="empty-state">
                            <i class="fas fa-crosshairs"></i>
                            <p>No kills recorded yet</p>
                        </div>`;
                    return;
                }

                let html = '';
                kills.forEach(kill => {
                    html += `
                        <a href="https://zkillboard.com/kill/${kill.killmail_id}/"
                            target="_blank"
                            class="kill-card p-3 mb-2 d-flex align-items-center text-decoration-none"
                            title="View on zKillboard">
                            <div class="ship-render me-3">
                                <img src="https://images.evetech.net/types/${kill.ship_type_id}/render?size=64"
                                    alt="${kill.ship_type_name}"
                                    class="rounded"
                                    loading="lazy">
                            </div>
                            <div class="flex-grow-1 min-width-0">
                                <div class="d-flex justify-content-between align-items-start">
                                    <strong class="text-truncate text-light" title="${kill.ship_type_name}">${kill.ship_type_name}</strong>
                                    <span class="text-success isk-value ms-2">${kill.total_value_formatted}</span>
                                </div>
                                <small class="text-muted text-truncate d-block" title="${kill.victim_name} (${kill.victim_corp_name})">
                                    ${kill.victim_name} (${kill.victim_corp_name})
                                </small>
                            </div>
                            <span class="ms-2 text-muted">
                                <i class="fas fa-external-link-alt"></i>
                            </span>
                        </a>`;
                });

                container.innerHTML = html;
            })
            .catch(error => {
                console.error('Error loading top kills:', error);
                container.innerHTML = `
                    <div class="empty-state">
                        <i class="fas fa-exclamation-triangle"></i>
                        <p>Error loading kills</p>
                    </div>`;
            });
    }

    /**
     * Initialize leaderboard DataTable
     */
    function initLeaderboard() {
        const table = document.getElementById('leaderboard-table');
        if (!table || !$.fn.DataTable) return;

        if (leaderboardTable) {
            leaderboardTable.destroy();
        }

        leaderboardTable = $('#leaderboard-table').DataTable({
            ajax: {
                url: getApiUrl('leaderboard'),
                dataSrc: 'data'
            },
            columns: [
                {
                    data: 'character_name',
                    render: function(data, type, row) {
                        if (type !== 'display') return data;

                        let rankBadge = '';
                        if (row.rank === 1) {
                            rankBadge = '<span class="rank-badge rank-1"><i class="fas fa-trophy"></i></span>';
                        } else if (row.rank === 2) {
                            rankBadge = '<span class="rank-badge rank-2">2</span>';
                        } else if (row.rank === 3) {
                            rankBadge = '<span class="rank-badge rank-3">3</span>';
                        } else {
                            rankBadge = '<span class="rank-badge rank-other">' + row.rank + '</span>';
                        }

                        return `
                            <div class="character-cell">
                                ${rankBadge}
                                <img src="https://images.evetech.net/characters/${row.portrait_id}/portrait?size=64"
                                    class="character-portrait"
                                    alt="${data}"
                                    loading="lazy">
                                <span>${data}</span>
                            </div>`;
                    }
                },
                {
                    data: 'kills',
                    className: 'text-center'
                },
                {
                    data: 'final_blows',
                    className: 'text-center'
                },
                {
                    data: 'kill_value',
                    className: 'text-end',
                    render: function(data, type, row) {
                        if (type === 'display') {
                            return row.kill_value_formatted + ' ISK';
                        }
                        return data;
                    }
                }
            ],
            order: [[3, 'desc']],
            serverSide: true,
            processing: true,
            pageLength: 10,
            lengthMenu: [10, 25, 50],
            language: {
                processing: '<div class="loading-spinner"></div>',
                emptyTable: 'No activity recorded yet',
                zeroRecords: 'No matching pilots found'
            }
        });
    }

    /**
     * Load recent kills tab
     */
    function loadRecentKills() {
        const container = document.getElementById('recent-kills-list');
        if (!container) return;

        container.innerHTML = '<div class="loading-spinner"></div>';

        const url = getApiUrl('recentKills') + (currentYear ? '&' : '?') + 'limit=50';

        fetch(url)
            .then(response => response.json())
            .then(data => {
                const kills = data.data || [];

                if (kills.length === 0) {
                    container.innerHTML = `
                        <div class="empty-state">
                            <i class="fas fa-clock"></i>
                            <p>No recent activity</p>
                        </div>`;
                    return;
                }

                let html = '';
                kills.forEach(kill => {
                    const isLoss = kill.is_loss;
                    const date = new Date(kill.killmail_time);
                    const timeStr = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

                    html += `
                        <div class="killmail-row ${isLoss ? 'is-loss' : 'is-kill'}">
                            <div class="d-flex align-items-center">
                                <img src="https://images.evetech.net/types/${kill.ship_type_id}/render?size=32"
                                    class="me-3 rounded"
                                    alt="${kill.ship_type_name}"
                                    loading="lazy">
                                <div class="flex-grow-1 min-width-0">
                                    <div class="d-flex justify-content-between">
                                        <a href="https://zkillboard.com/kill/${kill.killmail_id}/"
                                            target="_blank"
                                            class="text-info text-decoration-none fw-bold text-truncate">
                                            ${kill.ship_type_name}
                                        </a>
                                        <span class="${isLoss ? 'text-danger' : 'text-success'} ms-2">
                                            ${kill.total_value_formatted}
                                        </span>
                                    </div>
                                    <small class="text-muted">
                                        ${kill.victim_name} - ${kill.solar_system_name}
                                    </small>
                                </div>
                                <div class="text-end ms-3">
                                    <div class="small ${isLoss ? 'text-danger' : 'text-success'}">
                                        <i class="fas ${isLoss ? 'fa-times-circle' : 'fa-check-circle'}"></i>
                                        ${isLoss ? 'Loss' : 'Kill'}
                                    </div>
                                    <small class="text-muted">${timeStr}</small>
                                </div>
                            </div>
                        </div>`;
                });

                container.innerHTML = html;
            })
            .catch(error => {
                console.error('Error loading recent kills:', error);
                container.innerHTML = `
                    <div class="empty-state">
                        <i class="fas fa-exclamation-triangle"></i>
                        <p>Error loading kills</p>
                    </div>`;
            });
    }

    /**
     * Load my activity tab
     */
    function loadMyActivity() {
        const url = getApiUrl('myStats');

        fetch(url)
            .then(response => response.json())
            .then(data => {
                // Update personal stats
                const myKills = document.getElementById('my-kills');
                const myLosses = document.getElementById('my-losses');
                const myRank = document.getElementById('my-rank');
                const myEfficiency = document.getElementById('my-efficiency');
                const myKillValue = document.getElementById('my-kill-value');
                const myFavoriteShip = document.getElementById('my-favorite-ship');

                if (myKills) animateCounter(myKills, data.kills);
                if (myLosses) animateCounter(myLosses, data.losses);
                if (myRank) myRank.textContent = data.rank ? '#' + data.rank : '--';
                if (myEfficiency) myEfficiency.textContent = data.efficiency + '%';
                if (myKillValue) myKillValue.textContent = data.kill_value_formatted + ' ISK';
                if (myFavoriteShip) myFavoriteShip.textContent = data.favorite_ship || '--';
            })
            .catch(error => {
                console.error('Error loading my stats:', error);
            });

        // Load personal recent kills
        loadMyRecentKills();
    }

    /**
     * Load personal recent kills
     */
    function loadMyRecentKills() {
        const container = document.getElementById('my-recent-kills');
        if (!container) return;

        container.innerHTML = '<div class="loading-spinner"></div>';

        const url = getApiUrl('recentKills') + (currentYear ? '&' : '?') + 'limit=20&user_only=true';

        fetch(url)
            .then(response => response.json())
            .then(data => {
                const kills = data.data || [];

                if (kills.length === 0) {
                    container.innerHTML = `
                        <div class="empty-state">
                            <i class="fas fa-user-clock"></i>
                            <p>No personal activity this month</p>
                        </div>`;
                    return;
                }

                let html = '';
                kills.forEach(kill => {
                    const isLoss = kill.is_loss;
                    const date = new Date(kill.killmail_time);
                    const timeStr = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

                    html += `
                        <div class="killmail-row ${isLoss ? 'is-loss' : 'is-kill'}">
                            <div class="d-flex align-items-center">
                                <img src="https://images.evetech.net/types/${kill.ship_type_id}/render?size=32"
                                    class="me-2 rounded"
                                    alt="${kill.ship_type_name}"
                                    loading="lazy">
                                <div class="flex-grow-1">
                                    <a href="https://zkillboard.com/kill/${kill.killmail_id}/"
                                        target="_blank"
                                        class="text-info text-decoration-none">
                                        ${kill.ship_type_name}
                                    </a>
                                    <span class="${isLoss ? 'text-danger' : 'text-success'} ms-2">
                                        ${kill.total_value_formatted}
                                    </span>
                                </div>
                                <small class="text-muted">${timeStr}</small>
                            </div>
                        </div>`;
                });

                container.innerHTML = html;
            })
            .catch(error => {
                console.error('Error loading my kills:', error);
                container.innerHTML = `
                    <div class="empty-state">
                        <i class="fas fa-exclamation-triangle"></i>
                        <p>Error loading your activity</p>
                    </div>`;
            });
    }

    /**
     * Navigate to previous/next month
     * @param {number} direction - -1 for previous, 1 for next
     */
    function navigateMonth(direction) {
        let newMonth = currentMonth + direction;
        let newYear = currentYear;

        if (newMonth < 1) {
            newMonth = 12;
            newYear--;
        } else if (newMonth > 12) {
            newMonth = 1;
            newYear++;
        }

        // Don't allow future months
        const now = new Date();
        const targetDate = new Date(newYear, newMonth - 1, 1);
        if (targetDate > now) {
            return;
        }

        // Navigate to historical view or dashboard
        const isCurrentMonth = (newYear === now.getFullYear() && newMonth === now.getMonth() + 1);

        if (isCurrentMonth) {
            window.location.href = window.AAC_URLS.dashboard;
        } else {
            window.location.href = window.AAC_URLS.historical
                .replace('9999', newYear)
                .replace('99', newMonth);
        }
    }

    /**
     * Initialize all dashboard components
     */
    function init() {
        // Get current year/month from page
        currentYear = window.AAC_CURRENT_YEAR || new Date().getFullYear();
        currentMonth = window.AAC_CURRENT_MONTH || new Date().getMonth() + 1;

        // Load all data
        loadStats();
        loadActivityChart();
        loadShipClassChart();
        loadTopKills();
        initLeaderboard();

        // Setup tab change handlers
        const tabElements = document.querySelectorAll('button[data-bs-toggle="tab"]');
        tabElements.forEach(tab => {
            tab.addEventListener('shown.bs.tab', function(event) {
                const targetId = event.target.getAttribute('data-bs-target');
                if (targetId === '#recent') {
                    loadRecentKills();
                } else if (targetId === '#my-activity') {
                    loadMyActivity();
                } else if (targetId === '#leaderboard') {
                    // Refresh DataTable columns when tab shown
                    if (leaderboardTable) {
                        leaderboardTable.columns.adjust();
                    }
                }
            });
        });

        // Setup month navigation
        const prevBtn = document.getElementById('prev-month');
        const nextBtn = document.getElementById('next-month');

        if (prevBtn) {
            prevBtn.addEventListener('click', function() {
                navigateMonth(-1);
            });
        }

        if (nextBtn) {
            nextBtn.addEventListener('click', function() {
                navigateMonth(1);
            });

            // Disable next button if we're at current month
            const now = new Date();
            if (currentYear === now.getFullYear() && currentMonth === now.getMonth() + 1) {
                nextBtn.disabled = true;
            }
        }
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Expose public API
    window.AACDashboard = {
        refresh: function() {
            loadStats();
            loadActivityChart();
            loadShipClassChart();
            loadTopKills();
            if (leaderboardTable) {
                leaderboardTable.ajax.reload();
            }
        },
        formatISK: formatISK
    };

})();
