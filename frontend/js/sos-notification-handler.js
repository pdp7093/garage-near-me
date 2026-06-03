/**
 * SOS Notification Handler
 * Controls high-priority looping notifications when mechanic takes action
 * Usage: Call stopSOSNotificationLoop(sosId) when mechanic accepts/declines SOS
 */

// ── Stop the looping SOS notification ──────────────────────────────────────
async function stopSOSNotificationLoop(sosId) {
    if (!sosId) {
        console.warn('❌ No SOS ID provided to stopSOSNotificationLoop');
        return;
    }

    try {
        if (navigator.serviceWorker && navigator.serviceWorker.controller) {
            console.log(`🛑 Stopping SOS notification loop for ID: ${sosId}`);
            navigator.serviceWorker.controller.postMessage({
                type: 'STOP_SOS_LOOP',
                sosId: sosId
            });
        } else {
            console.warn('⚠️ Service Worker not ready');
        }
    } catch (error) {
        console.error('❌ Error stopping SOS loop:', error);
    }
}

// ── Get list of currently active looping SOS alerts ─────────────────────────
async function getActiveSOSAlerts() {
    return new Promise((resolve, reject) => {
        try {
            if (!navigator.serviceWorker || !navigator.serviceWorker.controller) {
                console.warn('⚠️ Service Worker not ready');
                resolve([]);
                return;
            }

            const channel = new MessageChannel();
            
            channel.port1.onmessage = (e) => {
                if (e.data.type === 'ACTIVE_SOS_LIST') {
                    console.log(`📋 Active SOS alerts: ${e.data.sosIds.join(', ')}`);
                    resolve(e.data.sosIds);
                }
            };

            navigator.serviceWorker.controller.postMessage({
                type: 'GET_ACTIVE_SOS'
            }, [channel.port2]);

            // Timeout after 2 seconds
            setTimeout(() => resolve([]), 2000);
        } catch (error) {
            console.error('❌ Error getting active SOS alerts:', error);
            reject(error);
        }
    });
}

// ── Stop ALL active SOS loops (call when mechanic opens the dashboard) ───────
async function stopAllSOSLoops() {
    try {
        if (navigator.serviceWorker && navigator.serviceWorker.controller) {
            navigator.serviceWorker.controller.postMessage({ type: 'STOP_ALL_SOS_LOOPS' });
            console.log('⏹️ Requested SW to stop all SOS loops');
        }
    } catch (e) {
        console.error('❌ Error stopping all SOS loops:', e);
    }
}

// ── Integration point: Call this when mechanic accepts SOS ──────────────────
function handleSOSAccepted(sosId) {
    console.log(`✅ SOS ${sosId} accepted - stopping notification loop`);
    stopSOSNotificationLoop(sosId);
}

// ── Integration point: Call this when mechanic declines SOS ─────────────────
function handleSOSDeclined(sosId) {
    console.log(`❌ SOS ${sosId} declined - stopping notification loop`);
    stopSOSNotificationLoop(sosId);
}

// ── Example: After API call to accept SOS ──────────────────────────────────
// Usage in mechanic pages:
// 
// const sosId = '12345'; // from notification data
// const response = await fetch(`${API}/sos/${sosId}/accept`, {method: 'POST'});
// if (response.ok) {
//     handleSOSAccepted(sosId);  // ← This stops the looping notification
// }

// Exposed as globals for regular script usage (no module needed)
window.stopSOSNotificationLoop = stopSOSNotificationLoop;
window.stopAllSOSLoops = stopAllSOSLoops;
window.getActiveSOSAlerts = getActiveSOSAlerts;
window.handleSOSAccepted = handleSOSAccepted;
window.handleSOSDeclined = handleSOSDeclined;
