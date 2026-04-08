function bindModuleFrontend() {
    const form = document.getElementById("module-form");
    const resultBox = document.getElementById("module-result-box");
    const primaryInput = document.getElementById("module-primary-input");
    const suggestionCards = Array.from(document.querySelectorAll("[data-action]"));
    const scenePills = Array.from(document.querySelectorAll("[data-scene]"));

    if (!form || !resultBox) {
        return;
    }

    const moduleName = form.dataset.moduleName || "Current module";
    const resultTitle = form.dataset.resultTitle || `${moduleName} brief`;
    const draftKey = `module_frontend_draft_${moduleName}`;

    const focusPrimaryInput = () => {
        if (primaryInput) {
            primaryInput.focus();
        }
    };

    const syncPrimaryHeight = () => {
        if (!primaryInput) {
            return;
        }
        primaryInput.style.height = "auto";
        primaryInput.style.height = `${Math.max(primaryInput.scrollHeight, 180)}px`;
    };

    const persistDraft = () => {
        try {
            const data = {};
            for (const [key, value] of new FormData(form).entries()) {
                data[String(key)] = String(value);
            }
            sessionStorage.setItem(draftKey, JSON.stringify(data));
        } catch (error) {
            console.warn("module draft unavailable", error);
        }
    };

    const appendToPrimaryInput = (text) => {
        if (!primaryInput || !text) {
            return;
        }

        const normalized = String(text).trim();
        const current = primaryInput.value.trim();
        primaryInput.value = current ? `${current}\n${normalized}` : normalized;
        syncPrimaryHeight();
        persistDraft();
        focusPrimaryInput();
    };

    suggestionCards.forEach((card) => {
        card.addEventListener("click", () => {
            appendToPrimaryInput(card.dataset.action || "");
        });
    });

    scenePills.forEach((pill) => {
        pill.addEventListener("click", () => {
            appendToPrimaryInput(`Scene: ${pill.dataset.scene || ""}`);
        });
    });

    try {
        const prompt = sessionStorage.getItem("portal_prompt");
        if (prompt && primaryInput) {
            primaryInput.value = prompt;
            sessionStorage.removeItem("portal_prompt");
        }
        sessionStorage.removeItem("portal_module");
        const draft = sessionStorage.getItem(draftKey);
        if (draft) {
            const parsed = JSON.parse(draft);
            for (const [key, value] of Object.entries(parsed)) {
                const field = form.elements.namedItem(key);
                if (field && typeof field.value === "string" && !field.value.trim()) {
                    field.value = value;
                }
            }
        }
    } catch (error) {
        console.warn("session storage unavailable", error);
    }

    syncPrimaryHeight();

    Array.from(form.elements).forEach((field) => {
        if (!field || typeof field.addEventListener !== "function") {
            return;
        }
        field.addEventListener("input", () => {
            syncPrimaryHeight();
            persistDraft();
        });
        field.addEventListener("change", persistDraft);
    });

    if (primaryInput) {
        primaryInput.addEventListener("keydown", (event) => {
            if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
                event.preventDefault();
                form.requestSubmit();
            }
        });
    }

    form.addEventListener("submit", (event) => {
        event.preventDefault();

        const formData = new FormData(form);
        const entries = Array.from(formData.entries())
            .map(([key, value]) => ({
                key: String(key).trim(),
                value: String(value).trim(),
            }))
            .filter((item) => item.value);

        const highlighted = entries.slice(0, 3);
        const summary = highlighted.length
            ? highlighted.map((item) => `${item.key}: ${item.value}`).join(" | ")
            : "No structured input yet. Add a task, target, or operating context first.";

        resultBox.innerHTML = `
            <div class="module-panel-head">
                <small>Output Brief</small>
                <strong>${resultTitle}</strong>
            </div>
            <ul class="module-result-list">
                <li>${moduleName} intake captured: ${summary}</li>
                <li>The current screen is now aligned to the new visual shell and can continue into a real workflow or API handoff.</li>
                <li>Next step: confirm the main objective, then route this brief into the downstream module action.</li>
            </ul>
        `;

        try {
            sessionStorage.removeItem(draftKey);
        } catch (error) {
            console.warn("module draft unavailable", error);
        }
    });

    // Power Trading Module Enhancements
    if (moduleName === "电力交易") {
        enhancePowerTradingModule();
    }
}

function enhancePowerTradingModule() {
    // Add real-time price update simulation
    const metricCards = document.querySelectorAll('.module-metric-card');
    metricCards.forEach(card => {
        card.setAttribute('data-module', 'power-trading');
    });

    // Add hover effects to action cards
    const actionCards = document.querySelectorAll('.module-action-card');
    actionCards.forEach(card => {
        card.setAttribute('data-module', 'power-trading');
    });

    // Add data attributes to board section
    const boardSection = document.querySelector('.module-board-section');
    if (boardSection) {
        boardSection.setAttribute('data-module', 'power-trading');
    }

    // Simulate real-time price updates (demo only)
    const priceElement = document.querySelector('.module-metric-card strong');
    if (priceElement && priceElement.textContent.includes('428')) {
        let basePrice = 428.5;
        setInterval(() => {
            const fluctuation = (Math.random() - 0.5) * 2;
            basePrice = Math.max(400, Math.min(500, basePrice + fluctuation));
            priceElement.textContent = basePrice.toFixed(1);
        }, 5000);
    }

    // Add trend indicators animation
    const trendCells = document.querySelectorAll('td:nth-child(3)');
    trendCells.forEach(cell => {
        if (cell.textContent.includes('↗')) {
            cell.style.color = '#22a06b';
            cell.style.fontWeight = '600';
        } else if (cell.textContent.includes('↘')) {
            cell.style.color = '#dc2626';
            cell.style.fontWeight = '600';
        }
    });
}

bindModuleFrontend();
