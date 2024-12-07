chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.action === "updateBlockedSites") {
      const blockedSites = message.sites.map((site, index) => ({
        id: index + 1,
        priority: 1,
        action: { type: "block" },
        condition: { urlFilter: site, resourceTypes: ["main_frame"] }
      }));
  
      chrome.declarativeNetRequest.updateDynamicRules(
        {
          removeRuleIds: Array.from({ length: blockedSites.length }, (_, i) => i + 1),
          addRules: blockedSites
        },
        () => {
          if (chrome.runtime.lastError) {
            console.error(chrome.runtime.lastError.message);
          } else {
            sendResponse({ success: true });
          }
        }
      );
  
      return true; // Indicates async response.
    }
  });
  