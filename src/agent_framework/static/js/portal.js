function bindPortalDialog() {
    const form = document.getElementById("portal-dialog-form");
    const input = document.getElementById("route-search");
    const promptButtons = Array.from(document.querySelectorAll("[data-prompt]"));
    const draftKey = "portal_prompt_draft";

    if (!form || !input) {
        return;
    }

    const syncHeight = () => {
        input.style.height = "auto";
        input.style.height = `${Math.max(input.scrollHeight, 168)}px`;
    };

    try {
        const draft = sessionStorage.getItem(draftKey);
        if (draft && !input.value.trim()) {
            input.value = draft;
        }
    } catch (error) {
        console.warn("portal draft unavailable", error);
    }

    syncHeight();

    promptButtons.forEach((button) => {
        button.addEventListener("click", () => {
            const prompt = String(button.dataset.prompt || "").trim();
            if (!prompt) {
                return;
            }

            input.value = input.value.trim() ? `${input.value.trim()}\n${prompt}` : prompt;
            syncHeight();
            input.focus();
        });
    });

    input.addEventListener("input", () => {
        syncHeight();
        try {
            sessionStorage.setItem(draftKey, input.value);
        } catch (error) {
            console.warn("portal draft unavailable", error);
        }
    });

    input.addEventListener("keydown", (event) => {
        if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
            event.preventDefault();
            form.requestSubmit();
        }
    });

    form.addEventListener("submit", (event) => {
        event.preventDefault();

        const prompt = input.value.trim();
        if (prompt) {
            sessionStorage.setItem("portal_prompt", prompt);
            sessionStorage.setItem("portal_module", "guide");
            sessionStorage.removeItem(draftKey);
        }

        window.location.href = "/maintenance-assistant";
    });
}

bindPortalDialog();
