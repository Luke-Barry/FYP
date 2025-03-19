// Initialize chart variables
let chart = null;
let chartData = [];
let lastPrice = null;
let currentCandle = null;
let CANDLE_INTERVAL_MS = 15000; // Default to 15 second candlesticks
let allTrades = []; // Store all trades for recalculating candles
let processedOrderIds = new Set(); // Track which orders we've already processed
let chartInitialized = false; // Track if chart is initialized
let debugMode = true; // Enable detailed logging

// Available intervals in milliseconds
const intervals = {
    '15s': 15000,
    '30s': 30000,
    '1m': 60000,
    '5m': 300000,
    '15m': 900000,
    '1h': 3600000
};

// Debug logging function
function debug(message, data) {
    if (debugMode) {
        if (data) {
            console.log(`[CHART DEBUG] ${message}`, data);
        } else {
            console.log(`[CHART DEBUG] ${message}`);
        }
    }
}

// Initialize the chart
function initializeChart() {
    debug("Initializing chart");
    
    // Create ECharts instance
    chart = echarts.init(document.getElementById('chart-container'));
    
    // Add resize listener
    window.addEventListener('resize', () => {
        if (chart) {
            chart.resize();
        }
    });
    
    // Add interval button listeners
    const buttons = document.querySelectorAll('.interval-button');
    buttons.forEach(button => {
        button.addEventListener('click', () => {
            const interval = button.getAttribute('data-interval');
            if (intervals[interval]) {
                // Update active button
                buttons.forEach(b => b.classList.remove('active'));
                button.classList.add('active');
                
                // Update interval and recalculate candles
                CANDLE_INTERVAL_MS = intervals[interval];
                debug(`Changed interval to ${interval} (${CANDLE_INTERVAL_MS}ms)`);
                
                // Recalculate all candles with new interval
                chartData = [];
                currentCandle = null;
                recalculateCandles();
                updateChartConfig();
            }
        });
    });
    
    // Set 15s as default active button
    const defaultButton = document.querySelector('[data-interval="15s"]');
    if (defaultButton) {
        defaultButton.classList.add('active');
    }
    
    chartInitialized = true;
    debug("Chart initialized");
}

// Recalculate candles from all trades
function recalculateCandles() {
    debug(`Recalculating candles with interval ${CANDLE_INTERVAL_MS}ms`);
    
    // Sort trades by timestamp
    allTrades.sort((a, b) => a.timestamp - b.timestamp);
    
    // Clear existing candles
    chartData = [];
    currentCandle = null;
    
    // Process each trade
    allTrades.forEach(trade => {
        processTrade(trade.price, trade.timestamp);
    });
    
    debug(`Recalculated ${chartData.length} candles`);
}

// Process a new trade
function processTrade(price, timestamp) {
    const candleTime = Math.floor(timestamp / CANDLE_INTERVAL_MS) * CANDLE_INTERVAL_MS;
    
    if (!currentCandle || currentCandle.time !== candleTime) {
        // If we have a current candle, push it to chartData
        if (currentCandle) {
            chartData.push(currentCandle);
        }
        
        // Create a new candle
        currentCandle = {
            time: candleTime,
            open: price,
            high: price,
            low: price,
            close: price
        };
    } else {
        // Update current candle
        currentCandle.high = Math.max(currentCandle.high, price);
        currentCandle.low = Math.min(currentCandle.low, price);
        currentCandle.close = price;
    }
    
    // Update last price
    lastPrice = price;
}

// Update the chart with current data
function updateChart() {
    if (!chart) {
        console.error("Cannot update chart - chart instance not available");
        return;
    }
    
    updateChartConfig();
}

// Format a timestamp for display
function formatTimestamp(timestamp) {
    const date = new Date(timestamp);
    const hours = date.getHours().toString().padStart(2, '0');
    const minutes = date.getMinutes().toString().padStart(2, '0');
    const seconds = date.getSeconds().toString().padStart(2, '0');
    return `${hours}:${minutes}:${seconds}`;
}

// Configure the chart with updated data
function updateChartConfig() {
    // Create a copy of chartData and add the current candle
    const displayData = [...chartData];
    if (currentCandle) {
        displayData.push({...currentCandle});
    }
    
    debug(`Updating chart with ${displayData.length} candles`);
    
    // Format data for ECharts
    const timestamps = [];
    const values = [];
    
    // Sort data by time to ensure proper display
    displayData.sort((a, b) => a.time - b.time);
    
    // Calculate price range for buffer
    let minPrice = Infinity;
    let maxPrice = -Infinity;
    
    // First pass: find actual price range
    displayData.forEach(candle => {
        minPrice = Math.min(minPrice, candle.low);
        maxPrice = Math.max(maxPrice, candle.high);
    });
    
    // Calculate the smallest price increment in the data
    const priceRange = maxPrice - minPrice;
    const smallestIncrement = priceRange > 0 ? priceRange * 0.01 : maxPrice * 0.0001; // 1% of range or 0.01% of price if no range
    
    // Second pass: format data and adjust single-price candles
    displayData.forEach(candle => {
        timestamps.push(formatTimestamp(candle.time));
        
        if (candle.open === candle.close && candle.high === candle.low) {
            // For single-price candles, add a tiny offset that's smaller than the smallest increment
            const offset = smallestIncrement * 0.2; // Use 20% of the smallest increment
            values.push([
                candle.open,
                candle.close,
                candle.open - offset,
                candle.open + offset
            ]);
        } else {
            values.push([candle.open, candle.close, candle.low, candle.high]);
        }
    });
    
    // Add a small buffer to the price range for visual clarity
    const priceBuffer = priceRange > 0 ? priceRange * 0.1 : maxPrice * 0.001;
    minPrice -= priceBuffer;
    maxPrice += priceBuffer;
    
    // Set up chart options
    const option = {
        animation: false,
        tooltip: {
            trigger: 'axis',
            axisPointer: {
                type: 'cross'
            },
            formatter: function (params) {
                const data = params[0].data;
                return [
                    'Time: ' + params[0].axisValue,
                    'Open: ' + data[0].toFixed(2),
                    'Close: ' + data[1].toFixed(2),
                    'Low: ' + data[2].toFixed(2),
                    'High: ' + data[3].toFixed(2)
                ].join('<br/>');
            }
        },
        legend: {
            data: ['Price'],
            top: 0
        },
        grid: {
            left: '10%',
            right: '10%',
            bottom: '15%',
            top: '5%',
            containLabel: true
        },
        xAxis: {
            type: 'category',
            data: timestamps,
            scale: true,
            boundaryGap: true,
            axisLine: { onZero: false },
            splitLine: { show: false },
            splitNumber: 20,
            min: 'dataMin',
            max: 'dataMax',
            axisLabel: {
                formatter: function (value) {
                    return value;
                }
            }
        },
        yAxis: {
            scale: true,
            splitArea: {
                show: true
            },
            min: minPrice,
            max: maxPrice,
            splitNumber: 8,
            axisLabel: {
                formatter: function (value) {
                    return value.toFixed(2);
                }
            }
        },
        dataZoom: [
            {
                type: 'inside',
                start: 0,
                end: 100,
                minValueSpan: 10
            },
            {
                show: true,
                type: 'slider',
                top: '90%',
                start: 0,
                end: 100
            }
        ],
        series: [
            {
                name: 'Price',
                type: 'candlestick',
                data: values,
                itemStyle: {
                    color: '#26a69a',
                    color0: '#ef5350',
                    borderColor: '#26a69a',
                    borderColor0: '#ef5350'
                },
                barWidth: '70%',
                barMaxWidth: 20,
                barMinWidth: 5,
            }
        ]
    };
    
    // Add price marker line if we have a last price
    if (lastPrice !== null) {
        debug(`Adding price marker at ${lastPrice}`);
        
        option.series.push({
            name: 'Last Price',
            type: 'line',
            data: Array(timestamps.length).fill(lastPrice),
            markLine: {
                data: [
                    {
                        yAxis: lastPrice,
                        label: {
                            formatter: lastPrice.toFixed(2)
                        }
                    }
                ],
                symbol: ['none', 'none'],
                lineStyle: {
                    color: '#4682B4',
                    width: 2,
                    type: 'dashed'
                }
            },
            symbol: 'none'
        });
    }
    
    // Apply options to chart
    try {
        chart.setOption(option, true);
        debug("Chart updated successfully");
    } catch (error) {
        console.error("Error updating chart:", error);
    }
}

// Process notifications to update candlestick data
function updateChartFromNotifications(notifications) {
    debug(`Processing ${notifications ? notifications.length : 0} notifications`);
    
    // Ensure chart is initialized
    if (!chartInitialized || !chart) {
        debug("Chart not initialized, initializing now");
        initializeChart();
        
        // Give chart time to initialize before processing data
        setTimeout(() => {
            processMatchedOrders(notifications);
        }, 200);
        return;
    }
    
    // Process notifications immediately if chart is already initialized
    processMatchedOrders(notifications);
}

// Process matched orders from notifications
function processMatchedOrders(notifications) {
    if (!notifications || notifications.length === 0) {
        debug("No notifications to process");
        return;
    }
    
    debug(`Processing ${notifications.length} notifications for matched orders`);
    
    // Filter to just ORDER_MATCHED notifications
    const matchedOrders = notifications.filter(n => n.type === 'ORDER_MATCHED');
    debug(`Found ${matchedOrders.length} matched orders in notifications`);
    
    if (matchedOrders.length === 0) {
        return;
    }
    
    let updated = false;
    
    // Process each matched order
    matchedOrders.forEach(notification => {
        debug("Processing matched order:", notification);
        
        if (!notification.price || !notification.quantity) {
            debug("Skipping matched order with missing price or quantity");
            return;
        }
        
        // Generate a unique ID for this order match
        const orderId = notification.order_id || `match-${Date.now()}-${Math.random()}`;
        
        // Skip if already processed
        if (processedOrderIds.has(orderId)) {
            debug(`Skipping already processed order: ${orderId}`);
            return;
        }
        
        // Mark as processed
        processedOrderIds.add(orderId);
        debug(`Processing new matched order ${orderId}`);
        
        const price = parseFloat(notification.price);
        
        // Ensure we have a timestamp or use current time
        let timestamp = Date.now(); // Default to current time
        
        if (notification.timestamp) {
            // Try to parse the timestamp
            const parsedTimestamp = parseInt(notification.timestamp);
            if (!isNaN(parsedTimestamp)) {
                timestamp = parsedTimestamp;
            }
        }
        
        debug(`Trade details: price=${price}, timestamp=${timestamp} (${new Date(timestamp).toISOString()})`);
        
        // Add to our historical trades array
        allTrades.push({
            price: price,
            quantity: parseFloat(notification.quantity),
            timestamp: timestamp,
            id: orderId
        });
        
        // Process this trade for the current candle (but don't update chart yet)
        processTrade(price, timestamp);
        updated = true;
    });
    
    // If data was updated, update the chart once at the end
    if (updated) {
        debug("Trade data updated, updating chart");
        updateChart();
    }
}

// Expose functions for use in the main script
window.initializeChart = initializeChart;
window.updateChartFromNotifications = updateChartFromNotifications;
window.processTrade = processTrade;
window.updateChart = updateChart;
