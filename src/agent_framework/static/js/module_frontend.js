function bindModuleFrontend() {
    const form = document.getElementById("module-form");
    const resultBox = document.getElementById("module-result-box");
    const primaryInput = document.getElementById("module-primary-input");
    const suggestionCards = Array.from(document.querySelectorAll("[data-action]"));
    const scenePills = Array.from(document.querySelectorAll("[data-scene]"));
    const filterPills = Array.from(document.querySelectorAll(".module-filter-pill"));

    if (!form || !resultBox) {
        return;
    }

    const moduleName = form.dataset.moduleName || "当前模块";
    const moduleSlug = form.dataset.moduleSlug || "";
    const resultTitle = form.dataset.resultTitle || `${moduleName}摘要`;
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
            suggestionCards.forEach((item) => item.classList.remove("is-selected"));
            card.classList.add("is-selected");
            appendToPrimaryInput(card.dataset.action || "");
        });
    });

    scenePills.forEach((pill) => {
        pill.addEventListener("click", () => {
            scenePills.forEach((item) => item.classList.remove("is-selected"));
            pill.classList.add("is-selected");
            appendToPrimaryInput(`场景：${pill.dataset.scene || ""}`);
        });
    });

    filterPills.forEach((pill) => {
        pill.addEventListener("click", () => {
            filterPills.forEach((item) => item.classList.remove("is-active", "is-selected"));
            pill.classList.add("is-active", "is-selected");
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
        const entryMap = Object.fromEntries(entries.map((item) => [item.key, item.value]));

        const selectedAction = document.querySelector(".module-suggestion-card.is-selected strong")?.textContent?.trim();
        const selectedScene = document.querySelector(".module-scene-pill.is-selected")?.textContent?.trim();
        const summaryLines = buildModuleSummary({
            moduleSlug,
            moduleName,
            entryMap,
            selectedAction,
            selectedScene,
        });

        resultBox.innerHTML = `
            <div class="module-panel-head">
                <small>输出摘要</small>
                <strong>${resultTitle}</strong>
            </div>
            <ul class="module-result-list">
                ${summaryLines.map((line) => `<li>${line}</li>`).join("")}
            </ul>
        `;

        try {
            sessionStorage.removeItem(draftKey);
        } catch (error) {
            console.warn("module draft unavailable", error);
        }
    });

    if (moduleName === "电力交易") {
        enhancePowerTradingModule();
    }
}

function buildModuleSummary({ moduleSlug, moduleName, entryMap, selectedAction, selectedScene }) {
    const valueOf = (key, fallback) => entryMap[key] || fallback;
    const actionText = selectedAction ? `已选快捷动作：${selectedAction}` : "未选择快捷动作";
    const sceneText = selectedScene ? `场景标签：${selectedScene}` : "未附加场景标签";

    const builders = {
        "weather-siting": () => ([
            `${moduleName}已收敛本轮项目边界：${valueOf("project", "项目名称待补")} / ${valueOf("region", "区域范围待补")} / ${valueOf("capacity", "容量与机型边界待补")}。`,
            `本轮比选目标为：${valueOf("goal", "比选目标待补")}。${actionText}，${sceneText}。`,
            "建议下一步先完成硬约束筛除和接入复筛，再输出优选、备选与踏勘清单。",
        ]),
        "smart-workorder": () => ([
            `${moduleName}已完成受理骨架：站点 ${valueOf("site", "待补")}，设备 ${valueOf("asset", "待补")}，等级 ${valueOf("severity", "待补")}。`,
            `故障与处置背景：${valueOf("issue", "待补充故障现象、影响范围和临时措施")}。${actionText}，${sceneText}。`,
            "建议下一步先锁定责任班组和备件命中，再把执行留痕与验收回执拉进同一闭环。",
        ]),
        "power-trading": () => ([
            `${moduleName}已锁定交易窗口：${valueOf("period", "交易时段待补")} / ${valueOf("market", "目标市场待补")} / ${valueOf("portfolio", "组合仓位待补")}。`,
            `当前风险边界：${valueOf("capacity", "风险边界待补")}；策略目标：${valueOf("goal", "策略目标待补")}。${actionText}，${sceneText}。`,
            "建议下一步同步生成主策略和备用策略，并把偏差敞口、止损线和盘后复盘口径一起带出。",
        ]),
        "smart-office": () => ([
            `${moduleName}已收口场景信息：${valueOf("topic", "办公场景待补")} / ${valueOf("subject", "会议或项目主题待补")} / ${valueOf("team", "协同部门待补")}。`,
            `本轮处理目标：${valueOf("goal", "请补充纪要口径、任务拆解和知识沉淀目标")}。${actionText}，${sceneText}。`,
            "建议下一步先确认 owner、deadline 和待确认项，再决定哪些内容进入纪要、任务和知识三条链路。",
        ]),
    };

    if (builders[moduleSlug]) {
        return builders[moduleSlug]();
    }

    const highlighted = Object.entries(entryMap).slice(0, 3);
    const summary = highlighted.length
        ? highlighted.map(([key, value]) => `${key}: ${value}`).join(" | ")
        : "当前还没有有效输入，建议先补任务对象、目标和业务背景。";

    return [
        `${moduleName} 已受理本轮输入：${summary}`,
        `${actionText}，${sceneText}。`,
        "建议下一步确认主目标、风险边界和责任节点，再继续流转到下游业务动作。",
    ];
}

function enhancePowerTradingModule() {
    const metricCards = document.querySelectorAll(".module-metric-card");
    metricCards.forEach((card) => {
        card.setAttribute("data-module", "power-trading");
    });

    const actionCards = document.querySelectorAll(".module-suggestion-card");
    actionCards.forEach((card) => {
        card.setAttribute("data-module", "power-trading");
    });

    const boardSection = document.querySelector(".module-board-section");
    if (boardSection) {
        boardSection.setAttribute("data-module", "power-trading");
    }

    const priceElement = document.querySelector(".module-metric-card strong");
    if (priceElement && priceElement.textContent.includes("428")) {
        let basePrice = 428.5;
        setInterval(() => {
            const fluctuation = (Math.random() - 0.5) * 2;
            basePrice = Math.max(400, Math.min(500, basePrice + fluctuation));
            priceElement.textContent = basePrice.toFixed(1);
        }, 5000);
    }

    const trendCells = document.querySelectorAll("td:nth-child(3)");
    trendCells.forEach((cell) => {
        if (cell.textContent.includes("↗")) {
            cell.style.color = "#22a06b";
            cell.style.fontWeight = "600";
        } else if (cell.textContent.includes("↘")) {
            cell.style.color = "#dc2626";
            cell.style.fontWeight = "600";
        }
    });
}

bindModuleFrontend();
