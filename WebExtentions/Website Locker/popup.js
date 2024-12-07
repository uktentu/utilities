document.addEventListener("DOMContentLoaded", () => {
    const websiteInput = document.getElementById("website");
    const addSiteButton = document.getElementById("addSite");
    const blockedList = document.getElementById("blockedList");
    const passwordInput = document.getElementById("password");
    const authenticateButton = document.getElementById("authenticate");
    const authError = document.getElementById("auth-error");
    const siteSection = document.getElementById("site-section");
    const authSection = document.getElementById("auth-section");
  
    const storedPassword = "Uday.2244"; // Replace with your preferred password
    let sites = [];
  
    chrome.storage.sync.get("blockedSites", (data) => {
      sites = data.blockedSites || [];
      sites.forEach(addSiteToUI);
    });
  
    // Authenticate user
    authenticateButton.addEventListener("click", () => {
      const enteredPassword = passwordInput.value.trim();
      if (enteredPassword === storedPassword) {
        authSection.style.display = "none";
        siteSection.style.display = "block";
        authError.style.display = "none";
      } else {
        authError.style.display = "block";
      }
    });
  
    // Add a website to the blocklist
    addSiteButton.addEventListener("click", () => {
      const site = websiteInput.value.trim();
      if (site && !sites.includes(site)) {
        sites.push(site);
        chrome.storage.sync.set({ blockedSites: sites });
        chrome.runtime.sendMessage(
          { action: "updateBlockedSites", sites },
          (response) => {
            if (response.success) {
              addSiteToUI(site);
            }
          }
        );
        websiteInput.value = "";
      }
    });
  
    // Add a website to the UI list
    function addSiteToUI(site) {
      const li = document.createElement("li");
      li.textContent = site;
      const removeButton = document.createElement("button");
      removeButton.textContent = "Remove";
      removeButton.addEventListener("click", () => {
        removeSiteFromList(site);
      });
      li.appendChild(removeButton);
      blockedList.appendChild(li);
    }
  
    // Remove a website from the blocklist
    function removeSiteFromList(site) {
      sites = sites.filter((item) => item !== site);
      chrome.storage.sync.set({ blockedSites: sites });
      chrome.runtime.sendMessage(
        { action: "updateBlockedSites", sites },
        (response) => {
          if (response.success) {
            // Remove from the UI as well
            const listItems = blockedList.querySelectorAll("li");
            listItems.forEach((li) => {
              if (li.textContent === site) {
                li.remove();
              }
            });
          }
        }
      );
    }
  });
  