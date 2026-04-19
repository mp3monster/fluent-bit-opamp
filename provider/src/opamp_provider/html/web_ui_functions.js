    async function fetchSettings() {
      const resp = await apiFetch("/api/settings/comms");
      if (!resp.ok) return;
      const data = await resp.json();
      state.delayed = data.delayed_comms_seconds ?? 60;
      state.significant = data.significant_comms_seconds ?? 300;
      state.clientEventHistorySize = data.client_event_history_size ?? 50;
      state.stateSaveFolder = String(data.state_save_folder || "runtime");
      const retentionCount = parseInt(data.retention_count, 10);
      state.retentionCount =
        Number.isNaN(retentionCount) || retentionCount <= 0
          ? 5
          : retentionCount;
      const snapshotFileCount = parseInt(data.state_snapshot_file_count, 10);
      state.stateSnapshotFileCount =
        Number.isNaN(snapshotFileCount) || snapshotFileCount < 0
          ? 0
          : snapshotFileCount;
      const autosaveInterval = parseInt(
        data.autosave_interval_seconds_since_change,
        10
      );
      state.autosaveIntervalSecondsSinceChange =
        Number.isNaN(autosaveInterval) || autosaveInterval <= 0
          ? 600
          : autosaveInterval;
      state.humanInLoopApproval = data.human_in_loop_approval === true;
      state.tlsEnabled = data.tls_enabled === true;
      state.httpsCertificateExpiryDate =
        typeof data.https_certificate_expiry_date === "string"
          ? data.https_certificate_expiry_date
          : null;
      state.httpsCertificateDaysRemaining =
        Number.isInteger(data.https_certificate_days_remaining)
          ? data.https_certificate_days_remaining
          : null;
      state.httpsCertificateExpiringSoon =
        data.https_certificate_expiring_soon === true;
      updatePendingApprovalVisibility();
    }

    function renderHttpsCertificateExpiryRow() {
      if (!httpsCertificateExpiryGroup || !httpsCertificateExpiryOutput) return;
      if (state.tlsEnabled !== true) {
        httpsCertificateExpiryGroup.classList.add("hidden");
        httpsCertificateExpiryGroup.classList.remove("expiring-soon");
        httpsCertificateExpiryOutput.textContent = "--";
        return;
      }
      httpsCertificateExpiryGroup.classList.remove("hidden");
      const expiryDate = state.httpsCertificateExpiryDate;
      if (expiryDate) {
        const daysRemaining = state.httpsCertificateDaysRemaining;
        if (Number.isInteger(daysRemaining)) {
          httpsCertificateExpiryOutput.textContent =
            `${expiryDate} (${daysRemaining} day${daysRemaining === 1 ? "" : "s"} remaining)`;
        } else {
          httpsCertificateExpiryOutput.textContent = expiryDate;
        }
      } else {
        httpsCertificateExpiryOutput.textContent = "Unavailable";
      }
      const expiringSoon =
        state.httpsCertificateExpiringSoon === true
        || (
          Number.isInteger(state.httpsCertificateDaysRemaining)
          && state.httpsCertificateDaysRemaining <= 30
        );
      httpsCertificateExpiryGroup.classList.toggle("expiring-soon", expiringSoon);
    }

    async function fetchClientSettings() {
      const resp = await apiFetch("/api/settings/client");
      if (!resp.ok) return;
      const data = await resp.json();
      const defaultHeartbeatFrequency = parseInt(
        data.default_heartbeat_frequency,
        10
      );
      if (!Number.isNaN(defaultHeartbeatFrequency) && defaultHeartbeatFrequency > 0) {
        state.defaultHeartbeatFrequency = defaultHeartbeatFrequency;
      }
    }

    async function fetchDiagnosticSettings() {
      const resp = await apiFetch("/api/settings/diagnostic");
      if (!resp.ok) {
        state.diagnosticEnabled = false;
        state.statePersistenceEnabled = false;
        return;
      }
      const data = await resp.json();
      state.diagnosticEnabled = data.diagnostic_enabled === true;
      state.statePersistenceEnabled = data.state_persistence_enabled === true;
    }

    async function loadServerOpampConfigTab() {
      if (!state.diagnosticEnabled) {
        serverOpampConfigPathOutput.textContent = "Diagnostic mode disabled";
        serverOpampConfigOutput.textContent =
          "Diagnostic mode disabled. Start server with --diagnostic to enable this tab.";
        return;
      }
      const resp = await apiFetch("/api/settings/server-opamp-config");
      if (!resp.ok) {
        if (resp.status === 403) {
          serverOpampConfigPathOutput.textContent = "Diagnostic mode disabled";
          serverOpampConfigOutput.textContent =
            "Diagnostic mode disabled. Restart server with --diagnostic.";
          return;
        }
        serverOpampConfigPathOutput.textContent = "Unavailable";
        serverOpampConfigOutput.textContent =
          "Failed to load provider config from server.";
        return;
      }
      const data = await resp.json();
      const configPath = String(data.config_path || "").trim();
      const configText = data.config_text;
      if (!configPath || typeof configText !== "string") {
        serverOpampConfigPathOutput.textContent = "Invalid payload";
        serverOpampConfigOutput.textContent =
          "Server returned an invalid diagnostic response payload.";
        return;
      }
      serverOpampConfigPathOutput.textContent = configPath;
      serverOpampConfigOutput.textContent = configText;
    }

    async function fetchGlobalSettingsHelp() {
      applyGlobalSettingsHelp(DEFAULT_GLOBAL_SETTINGS_HELP);
      const resp = await apiFetch("/api/help/global-settings");
      if (!resp.ok) return;
      const data = await resp.json();
      const fields = data && typeof data.fields === "object" ? data.fields : {};
      applyGlobalSettingsHelp(fields);
    }

    function applyGlobalSettingsHelp(fields) {
      const resolvedFields = {};
      Object.keys(DEFAULT_GLOBAL_SETTINGS_HELP).forEach(key => {
        const incoming = fields && typeof fields[key] === "object" ? fields[key] : {};
        resolvedFields[key] = {
          label: String(incoming.label || DEFAULT_GLOBAL_SETTINGS_HELP[key].label),
          tooltip: String(incoming.tooltip || DEFAULT_GLOBAL_SETTINGS_HELP[key].tooltip),
        };
      });
      const bindings = [
        {
          key: "delayed_comms_seconds",
          label: delayedCommsSecondsLabel,
          icon: document.querySelector('.help-icon[data-help-key="delayed_comms_seconds"]'),
        },
        {
          key: "significant_comms_seconds",
          label: significantCommsSecondsLabel,
          icon: document.querySelector('.help-icon[data-help-key="significant_comms_seconds"]'),
        },
        {
          key: "default_heartbeat_frequency",
          label: defaultHeartbeatFrequencyLabel,
          icon: document.querySelector('.help-icon[data-help-key="default_heartbeat_frequency"]'),
        },
        {
          key: "client_event_history_size",
          label: clientEventHistorySizeLabel,
          icon: document.querySelector('.help-icon[data-help-key="client_event_history_size"]'),
        },
        {
          key: "human_in_loop_approval",
          label: humanInLoopApprovalLabel,
          icon: document.querySelector('.help-icon[data-help-key="human_in_loop_approval"]'),
        },
        {
          key: "state_save_folder",
          label: stateSaveFolderLabel,
          icon: document.querySelector('.help-icon[data-help-key="state_save_folder"]'),
        },
        {
          key: "retention_count",
          label: retentionCountLabel,
          icon: document.querySelector('.help-icon[data-help-key="retention_count"]'),
        },
        {
          key: "autosave_interval_seconds_since_change",
          label: autosaveIntervalLabel,
          icon: document.querySelector('.help-icon[data-help-key="autosave_interval_seconds_since_change"]'),
        },
      ];
      bindings.forEach(binding => {
        const item = resolvedFields[binding.key];
        if (!item) return;
        if (binding.label) binding.label.textContent = item.label;
        if (binding.icon) {
          binding.icon.title = item.tooltip;
          binding.icon.dataset.helpText = item.tooltip;
          binding.icon.setAttribute("aria-label", `${item.label} help`);
        }
      });
      bindHelpIcons();
    }

    function bindHelpIcons() {
      document.querySelectorAll(".help-icon[data-help-key]").forEach(icon => {
        if (icon.dataset.helpBound === "true") return;
        icon.dataset.helpBound = "true";
        icon.addEventListener("click", event => {
          event.preventDefault();
          event.stopPropagation();
          const target = event.currentTarget;
          const tooltipText = String(target.dataset.helpText || target.title || "").trim();
          if (!tooltipText) return;
          if (activeHelpPopover && activeHelpIcon === target) {
            hideHelpPopover();
            return;
          }
          showHelpPopover(target, tooltipText);
        });
      });
    }

    function showHelpPopover(icon, tooltipText) {
      hideHelpPopover();
      const popover = document.createElement("div");
      popover.className = "help-popover";
      popover.setAttribute("role", "tooltip");
      popover.textContent = tooltipText;
      document.body.appendChild(popover);

      const iconRect = icon.getBoundingClientRect();
      const popoverRect = popover.getBoundingClientRect();
      let left = iconRect.left + (iconRect.width / 2) - (popoverRect.width / 2);
      left = Math.max(8, Math.min(left, window.innerWidth - popoverRect.width - 8));
      let top = iconRect.bottom + 8;
      if (top + popoverRect.height > window.innerHeight - 8) {
        top = iconRect.top - popoverRect.height - 8;
      }
      if (top < 8) top = 8;
      popover.style.left = `${left}px`;
      popover.style.top = `${top}px`;
      activeHelpPopover = popover;
      activeHelpIcon = icon;
    }

    function hideHelpPopover() {
      if (!activeHelpPopover) return;
      activeHelpPopover.remove();
      activeHelpPopover = null;
      activeHelpIcon = null;
    }

    async function fetchCustomCommands() {
      const clientId = activeClient && activeClient.client_id
        ? String(activeClient.client_id)
        : "";
      const query = clientId
        ? `?client_id=${encodeURIComponent(clientId)}`
        : "";
      const resp = await apiFetch(`/api/commands/custom${query}`);
      if (!resp.ok) return;
      const data = await resp.json();
      state.customCommands = Array.isArray(data.commands) ? data.commands : [];
    }

    function updatePendingApprovalCount(countValue) {
      const parsed = parseInt(countValue, 10);
      pendingApprovalCount.textContent = Number.isNaN(parsed) ? "0" : String(parsed);
    }

    function updatePendingApprovalVisibility() {
      const enabled = state.humanInLoopApproval === true;
      pendingApprovalPill.classList.toggle("hidden", !enabled);
      pendingApprovalPill.setAttribute("aria-hidden", enabled ? "false" : "true");
      pendingApprovalPill.tabIndex = enabled ? 0 : -1;
      if (!enabled && pendingApprovalModal.classList.contains("open")) {
        closePendingApprovalModal();
      }
    }

    async function fetchPendingApprovals() {
      if (state.humanInLoopApproval !== true) {
        state.pendingApprovals = [];
        updatePendingApprovalCount(0);
        return;
      }
      const resp = await apiFetch("/api/approvals/pending");
      if (!resp.ok) return;
      const data = await resp.json();
      state.pendingApprovals = Array.isArray(data.clients) ? data.clients : [];
      updatePendingApprovalCount(state.pendingApprovals.length);
      if (pendingApprovalModal.classList.contains("open")) {
        renderPendingApprovalTable();
      }
    }

    function normalizeFilterValue(value) {
      return String(value || "").trim();
    }

    function setFilterModeButtonState() {
      const isExclude = state.filters.invertFilter === true;
      filterModeBtn.textContent = isExclude ? "Exclude" : "Show";
      filterModeBtn.classList.toggle("exclude", isExclude);
      filterModeBtn.setAttribute("aria-pressed", isExclude ? "true" : "false");
    }

    function setFiltersCollapsed(collapsed) {
      const isCollapsed = collapsed === true;
      state.filters.collapsed = isCollapsed;
      filterControls.classList.toggle("collapsed", isCollapsed);
      toggleFiltersBtn.textContent = isCollapsed ? "Show Filters" : "Hide Filters";
      toggleFiltersBtn.setAttribute("aria-expanded", isCollapsed ? "false" : "true");
      toggleFiltersBtn.classList.toggle("closed", isCollapsed);
    }

    function setClientFilterState(filters = {}) {
      if (Object.prototype.hasOwnProperty.call(filters, "serviceInstanceId")) {
        state.filters.serviceInstanceId = normalizeFilterValue(filters.serviceInstanceId);
      }
      if (Object.prototype.hasOwnProperty.call(filters, "clientVersion")) {
        state.filters.clientVersion = normalizeFilterValue(filters.clientVersion);
      }
      if (Object.prototype.hasOwnProperty.call(filters, "hostName")) {
        state.filters.hostName = normalizeFilterValue(filters.hostName);
      }
      if (Object.prototype.hasOwnProperty.call(filters, "hostIp")) {
        state.filters.hostIp = normalizeFilterValue(filters.hostIp);
      }
      if (Object.prototype.hasOwnProperty.call(filters, "invertFilter")) {
        state.filters.invertFilter = filters.invertFilter === true;
      }
      if (Object.prototype.hasOwnProperty.call(filters, "collapsed")) {
        state.filters.collapsed = filters.collapsed === true;
      }
    }

    function readClientFiltersFromInputs() {
      return {
        serviceInstanceId: normalizeFilterValue(filterServiceInstanceInput.value),
        clientVersion: normalizeFilterValue(filterClientVersionInput.value),
        hostName: normalizeFilterValue(filterHostNameInput.value),
        hostIp: normalizeFilterValue(filterHostIpInput.value),
      };
    }

    function syncClientFiltersFromInputs() {
      setClientFilterState(readClientFiltersFromInputs());
    }

    function writeClientFiltersToInputs() {
      filterServiceInstanceInput.value = state.filters.serviceInstanceId;
      filterClientVersionInput.value = state.filters.clientVersion;
      filterHostNameInput.value = state.filters.hostName;
      filterHostIpInput.value = state.filters.hostIp;
      setFilterModeButtonState();
      setFiltersCollapsed(state.filters.collapsed);
    }

    function activeClientFilters(includeMode = false) {
      const active = [];
      if (state.filters.serviceInstanceId) {
        active.push(["service_instance_id", state.filters.serviceInstanceId]);
      }
      if (state.filters.clientVersion) {
        active.push(["client_version", state.filters.clientVersion]);
      }
      if (state.filters.hostName) {
        active.push(["host_name", state.filters.hostName]);
      }
      if (state.filters.hostIp) {
        active.push(["host_ip", state.filters.hostIp]);
      }
      if (includeMode && state.filters.invertFilter === true && active.length > 0) {
        active.push(["invertFilter", "true"]);
      }
      return active;
    }

    function activeFilterCount() {
      return activeClientFilters(false).length;
    }

    function updateActiveFiltersIndicator() {
      if (!activeFiltersIndicator) return;
      const activeCount = activeFilterCount();
      const mode = state.filters.invertFilter === true ? "exclude" : "show";
      if (activeCount === 0) {
        activeFiltersIndicator.textContent = "Filters: none";
      } else {
        activeFiltersIndicator.textContent = `Filters active: ${activeCount} (${mode})`;
      }
      activeFiltersIndicator.classList.toggle("active", activeCount > 0);
      if (clearFiltersBtn) {
        clearFiltersBtn.disabled = activeCount === 0;
      }
      toggleFiltersBtn.classList.toggle(
        "filters-active",
        state.filters.collapsed === true && activeCount > 0
      );
    }

    function buildClientFilterQueryString() {
      const params = new URLSearchParams();
      activeClientFilters(true).forEach(([key, value]) => {
        params.append(key, value);
      });
      return params.toString();
    }

    async function applyClientFilters() {
      syncClientFiltersFromInputs();
      state.page = 1;
      updateActiveFiltersIndicator();
      await fetchClients();
    }

    async function clearClientFilters() {
      setClientFilterState({
        serviceInstanceId: "",
        clientVersion: "",
        hostName: "",
        hostIp: "",
        invertFilter: false,
      });
      writeClientFiltersToInputs();
      state.page = 1;
      updateActiveFiltersIndicator();
      await fetchClients();
    }

    function toggleFilterMode() {
      state.filters.invertFilter = state.filters.invertFilter !== true;
      setFilterModeButtonState();
      updateActiveFiltersIndicator();
    }

    function toggleFiltersPanel() {
      setFiltersCollapsed(state.filters.collapsed !== true);
      updateActiveFiltersIndicator();
    }

    async function fetchClients() {
      const query = buildClientFilterQueryString();
      const endpoint = query ? `/api/clients?${query}` : "/api/clients";
      const resp = await apiFetch(endpoint);
      if (!resp.ok) return;
      const data = await resp.json();
      state.clients = data.clients || [];
      lastUpdated.textContent = new Date().toLocaleTimeString();
      const total = Number.isInteger(data.total) ? data.total : state.clients.length;
      agentCount.textContent = total;
      if (state.humanInLoopApproval === true) {
        updatePendingApprovalCount(data.pending_approval_total ?? state.pendingApprovals.length);
      } else {
        updatePendingApprovalCount(0);
      }
      renderTable();
      refreshOpenModal();
    }

    function totalPages() {
      return Math.max(1, Math.ceil(state.clients.length / state.pageSize));
    }

    function computeStatus(client) {
      if (client.disconnected) {
        return { label: "disconnected", cls: "disconnected" };
      }
      if (!client.last_communication) {
        return { label: "unknown", cls: "" };
      }
      const last = new Date(client.last_communication);
      const delta = (Date.now() - last.getTime()) / 1000;
      if (delta > state.significant) {
        return { label: "late", cls: "late-red" };
      }
      if (delta > state.delayed) {
        return { label: "delayed", cls: "late-amber" };
      }
      return { label: "ok", cls: "" };
    }

    function hasPending(client) {
      const hasConfig = Boolean(client.requested_config);
      const hasCommand = Array.isArray(client.commands) && client.commands.some(cmd => !cmd.sent_at);
      return hasConfig || hasCommand;
    }

    function renderTable() {
      const sorted = [...state.clients].sort((a, b) => {
        const dir = state.sortDir === "asc" ? 1 : -1;
        const av = a[state.sortKey] ?? "";
        const bv = b[state.sortKey] ?? "";
        return av > bv ? dir : av < bv ? -dir : 0;
      });

      const total = totalPages();
      const pagination = document.querySelector(".pagination");
      if (pagination) {
        pagination.style.display = total > 1 ? "flex" : "none";
      }
      if (state.page > total) state.page = total;
      const start = (state.page - 1) * state.pageSize;
      const pageItems = sorted.slice(start, start + state.pageSize);

      let amber = 0;
      let red = 0;
      clientBody.innerHTML = "";
      pageItems.forEach(client => {
        const status = computeStatus(client);
        if (!client.disconnected) {
          if (status.cls === "late-amber") amber += 1;
          if (status.cls === "late-red") red += 1;
        }

        const tr = document.createElement("tr");
        if (status.cls === "late-amber") tr.classList.add("row-amber");
        if (status.cls === "late-red") tr.classList.add("row-red");
        if (status.cls === "disconnected") tr.classList.add("row-disconnected");
        if (hasPending(client)) tr.classList.add("pending-border");
        tr.addEventListener("click", () => openModal(client));
        tr.addEventListener("contextmenu", event => {
          event.preventDefault();
          contextClient = client;
          contextMenu.style.left = `${event.clientX}px`;
          contextMenu.style.top = `${event.clientY}px`;
          contextMenu.classList.add("open");
        });

        const displayId = getClientDisplayId(client);
        tr.innerHTML = `
          <td>${displayId}</td>
          <td>${client.client_id ?? "--"}</td>
          <td><span class="status-dot ${status.cls}"><span class="dot"></span>${status.label}</span></td>
          <td>${client.last_communication ? new Date(client.last_communication).toLocaleString() : "--"}</td>
          <td>${client.current_config_version ?? "--"}</td>
          <td>${client.client_version ?? "--"}</td>
        `;
        clientBody.appendChild(tr);
      });

      amberCount.textContent = amber;
      redCount.textContent = red;
      pageNum.textContent = state.page;
      pageTotal.textContent = total;
      pageJump.value = state.page;
    }

    function activeTabName() {
      const activeBtn = tabButtons.find(btn => btn.classList.contains("active"));
      return activeBtn?.dataset.tab || "summary";
    }

    function refreshOpenModal() {
      if (!activeClient || !modal.classList.contains("open")) return;
      const refreshed = state.clients.find(
        clientEntry => clientEntry.client_id === activeClient.client_id
      );
      if (!refreshed) {
        closeModal();
        return;
      }
      openModal(refreshed, {
        preserveTab: true,
        customCommandState: captureCustomCommandState(),
        healthPanelOpen: !componentHealthPanel.classList.contains("hidden"),
      });
    }

    function openModal(client, options = {}) {
      const preserveTab = options.preserveTab === true;
      const desiredTab = preserveTab ? activeTabName() : "summary";
      const customCommandState = options.customCommandState || null;
      const preserveHealthPanel = options.healthPanelOpen === true;
      activeClient = client;
      const status = computeStatus(client);
      modalCard.classList.remove("late-amber", "late-red", "row-disconnected");
      if (status.cls === "late-amber") modalCard.classList.add("late-amber");
      if (status.cls === "late-red") modalCard.classList.add("late-red");
      if (status.cls === "disconnected") modalCard.classList.add("row-disconnected");

      modalFields.innerHTML = "";
      componentHealthPanel.classList.add("hidden");
      componentHealthBody.innerHTML = "";
      clientDataPanel.classList.add("hidden");
      clientDataYaml.textContent = "";
      toggleDataBtn.classList.remove("hidden");
      toggleDataBtn.textContent = "View Data";
      const agentDesc = client.agent_description || "";
      const serviceName = extractAgentField(agentDesc, "service.name");
      const serviceInstanceId = extractAgentField(agentDesc, "service.instance.id");
      const hostType = extractAgentField(agentDesc, "os_type");
      const hostVersion = extractAgentField(agentDesc, "os_version");
      const hostName = extractAgentField(agentDesc, "hostname");
      const macAddress = extractAgentField(agentDesc, "mac_address");
      const reportedIpAddress =
        extractAgentField(agentDesc, "ip_address")
        || extractAgentField(agentDesc, "ip")
        || extractAgentField(agentDesc, "host.ip");
      const sourceIpAddress = client && client.remote_addr ? String(client.remote_addr) : "";
      const ipAddress = reportedIpAddress || sourceIpAddress;
      const nextExpected = computeNextExpected(client);
      const instanceUid = client.client_id ?? "--";
      const titleName = serviceInstanceId || "Client";
      modalTitle.textContent = `${titleName} (${instanceUid})`;
      const healthInfo = getClientHealthInfo(client);
      const hasDisplayValue = value => typeof value === "string" && value.trim() !== "";

      const fields = [];
      fields.push([
        "Status",
        `<span class="status-dot modal-status ${status.cls}"><span class="dot"></span>${status.label}</span>`,
      ]);
      if (serviceName) {
        fields.push(["Service Name", serviceName, true]);
      }
      if (serviceInstanceId) {
        fields.push(["Service Instance ID", serviceInstanceId, true]);
      }
      fields.push(["Instance UID", instanceUid, true]);
      fields.push([
        "Health Status",
        healthInfo.hasComponents
          ? `<button type="button" class="data-toggle" title="click for more details" aria-label="click for more details"><span class="${healthInfo.textClass}">${healthInfo.summary}</span></button>`
          : `<span class="${healthInfo.textClass}">${healthInfo.summary}</span>`,
      ]);
      if (hostType) {
        fields.push(["Host Type", hostType]);
      }
      if (hostVersion) {
        fields.push(["Host Version", hostVersion]);
      }
      if (hostName) {
        fields.push(["Host Name", hostName]);
      }
      if (hasDisplayValue(macAddress)) {
        fields.push(["MAC Address", String(macAddress).trim()]);
      }
      if (hasDisplayValue(ipAddress)) {
        fields.push(["IP Address", String(ipAddress).trim()]);
      }
      fields.push(
        ["First Registered", client.first_seen ? new Date(client.first_seen).toLocaleString() : "--"],
        ["Last Communication", client.last_communication ? new Date(client.last_communication).toLocaleString() : "--"],
        ["Next Expected", nextExpected ? new Date(nextExpected).toLocaleString() : "--"],
        ["Requested Config", client.requested_config_version ?? "--"],
        ["Client Version", client.client_version ?? "--"],
        ["Last Channel", client.last_channel ?? "--"],
        ["Capabilities", renderCapabilitiesList(client.capabilities)],
      );
      fields.forEach(([label, value, fullWidth]) => {
        const div = document.createElement("div");
        div.className = "field";
        if (fullWidth === true) {
          div.classList.add("full-width");
        }
        div.innerHTML = `<label>${label}</label><div>${value}</div>`;
        if (label === "Health Status" && healthInfo.hasComponents) {
          const btn = div.querySelector("button");
          if (btn) {
            btn.addEventListener("click", () => {
              const isHidden = componentHealthPanel.classList.contains("hidden");
              if (isHidden) {
                renderComponentHealthMap(healthInfo.componentMap);
                componentHealthPanel.classList.remove("hidden");
              } else {
                componentHealthPanel.classList.add("hidden");
              }
            });
          }
        }
        modalFields.appendChild(div);
      });

      configInput.value = formatConfigValue(client.requested_config) || "";
      currentConfigOutput.textContent = formatConfigValue(client.current_config) || "--";
      if (preserveHealthPanel && healthInfo.hasComponents) {
        renderComponentHealthMap(healthInfo.componentMap);
        componentHealthPanel.classList.remove("hidden");
      }
      renderEventsHistory(client);
      renderCommandButtons(client, customCommandState);
      fetchCustomCommands().then(() => {
        if (!activeClient || activeClient.client_id !== client.client_id) return;
        const preserved = captureCustomCommandState();
        renderCommandButtons(activeClient, preserved);
      });
      let nextTab = desiredTab;
      if (nextTab === "history" && historyTabBtn.classList.contains("hidden")) {
        nextTab = "summary";
      }
      setActiveTab(nextTab);
      modal.classList.add("open");
    }

    function closeModal() {
      modal.classList.remove("open");
      activeClient = null;
      configInput.value = "";
      currentConfigOutput.textContent = "";
      eventsHistoryList.innerHTML = "";
      historyTabBtn.classList.add("hidden");
      componentHealthPanel.classList.add("hidden");
      componentHealthBody.innerHTML = "";
      toggleDataBtn.classList.remove("hidden");
      toggleDataBtn.textContent = "View Data";
    }

    function yamlScalar(value) {
      if (value === null || value === undefined) return "null";
      if (typeof value === "number" || typeof value === "boolean") return String(value);
      if (typeof value === "string") {
        if (value.includes("\n")) {
          return `|\n${value.split("\n").map(line => `  ${line}`).join("\n")}`;
        }
        const needsQuote = value === "" || /[:#\\[\\]{}&,*!?|>\\-]|^\\s|\\s$/.test(value);
        if (!needsQuote) return value;
        return `'${value.replace(/'/g, "''")}'`;
      }
      return String(value);
    }

    function toYaml(value, indent = 0) {
      const pad = " ".repeat(indent);
      if (Array.isArray(value)) {
        if (value.length === 0) return `${pad}[]`;
        return value
          .map(item => {
            if (item && typeof item === "object") {
              return `${pad}-\n${toYaml(item, indent + 2)}`;
            }
            return `${pad}- ${yamlScalar(item)}`;
          })
          .join("\n");
      }
      if (value && typeof value === "object") {
        const entries = Object.entries(value).sort(([a], [b]) => a.localeCompare(b));
        if (entries.length === 0) return `${pad}{}`;
        return entries
          .map(([key, val]) => {
            if (val && typeof val === "object") {
              return `${pad}${key}:\n${toYaml(val, indent + 2)}`;
            }
            const scalar = yamlScalar(val);
            if (typeof val === "string" && scalar.startsWith("|\n")) {
              return `${pad}${key}: ${scalar.replace(/\n/g, `\n${pad}  `)}`;
            }
            return `${pad}${key}: ${scalar}`;
          })
          .join("\n");
      }
      return `${pad}${yamlScalar(value)}`;
    }

    function normalizeClientData(client) {
      const clone = JSON.parse(JSON.stringify(client));
      const parseAgentDescription = (text) => {
        if (!text || typeof text !== "string") return text;
        const attrs = [];
        const patterns = [
          { type: "string", regex: /key: "([^"]+)"[\s\S]*?string_value: "([^"]*)"/g },
          { type: "bytes", regex: /key: "([^"]+)"[\s\S]*?bytes_value: "([^"]*)"/g },
          { type: "int", regex: /key: "([^"]+)"[\s\S]*?int_value: ([0-9-]+)/g },
          { type: "bool", regex: /key: "([^"]+)"[\s\S]*?bool_value: (true|false)/g },
          { type: "double", regex: /key: "([^"]+)"[\s\S]*?double_value: ([0-9eE+\\.-]+)/g },
        ];
        for (const pattern of patterns) {
          let match;
          while ((match = pattern.regex.exec(text)) !== null) {
            const key = match[1];
            let value = match[2];
            if (pattern.type === "int") value = parseInt(value, 10);
            if (pattern.type === "double") value = parseFloat(value);
            if (pattern.type === "bool") value = value === "true";
            attrs.push({ key, value, type: pattern.type });
          }
        }
        if (attrs.length === 0) return text;
        const map = {};
        attrs.forEach(item => {
          map[item.key] = item.value;
        });
        return { attributes: attrs, map };
      };
      const parseIfJson = (value) => {
        if (typeof value !== "string") return value;
        const trimmed = value.trim();
        if (!trimmed) return value;
        if (!(trimmed.startsWith("{") || trimmed.startsWith("["))) return value;
        try {
          return JSON.parse(trimmed);
        } catch {
          return value;
        }
      };
      clone.agent_description = parseAgentDescription(clone.agent_description);
      clone.current_config = parseIfJson(clone.current_config);
      clone.requested_config = parseIfJson(clone.requested_config);
      return clone;
    }

    function toggleClientData() {
      if (!activeClient) return;
      const hidden = clientDataPanel.classList.contains("hidden");
      if (hidden) {
        clientDataYaml.textContent = toYaml(normalizeClientData(activeClient));
        clientDataPanel.classList.remove("hidden");
        toggleDataBtn.classList.add("hidden");
      } else {
        clientDataPanel.classList.add("hidden");
        clientDataYaml.textContent = "";
        toggleDataBtn.classList.remove("hidden");
        toggleDataBtn.textContent = "View Data";
      }
    }

    function setActiveTab(tabName) {
      tabButtons.forEach(btn => {
        const isActive = btn.dataset.tab === tabName;
        btn.classList.toggle("active", isActive);
      });
      Object.entries(tabPanels).forEach(([key, panel]) => {
        panel.classList.toggle("active", key === tabName);
      });
    }

    function setActiveSettingsTab(tabName) {
      if (
        tabName === "server-opamp-config"
        && settingsTabServerOpampConfigBtn.classList.contains("hidden")
      ) {
        tabName = "server";
      }
      settingsTabButtons.forEach(btn => {
        const isActive = btn.dataset.settingsTab === tabName;
        btn.classList.toggle("active", isActive);
      });
      Object.entries(settingsTabPanels).forEach(([key, panel]) => {
        panel.classList.toggle("active", key === tabName);
      });
      hideHelpPopover();
      saveServerSettingsBtn.classList.toggle("hidden", tabName !== "server");
      saveGlobalSettingsBtn.classList.toggle("hidden", tabName === "server-opamp-config");
      if (tabName === "server-opamp-config") {
        void loadServerOpampConfigTab();
      }
    }

    async function openGlobalSettingsModal() {
      await fetchSettings();
      await fetchClientSettings();
      await fetchDiagnosticSettings();
      delayedCommsSecondsInput.value = String(state.delayed);
      significantCommsSecondsInput.value = String(state.significant);
      clientEventHistorySizeInput.value = String(state.clientEventHistorySize);
      stateSaveFolderInput.value = String(state.stateSaveFolder || "runtime");
      retentionCountInput.value = String(state.retentionCount);
      autosaveIntervalInput.value = String(state.autosaveIntervalSecondsSinceChange);
      humanInLoopApprovalInput.checked = state.humanInLoopApproval === true;
      renderHttpsCertificateExpiryRow();
      defaultHeartbeatFrequencyInput.value = String(state.defaultHeartbeatFrequency);
      settingsTabServerOpampConfigBtn.classList.toggle("hidden", !state.diagnosticEnabled);
      if (statePersistenceGroup) {
        statePersistenceGroup.classList.toggle(
          "hidden",
          state.statePersistenceEnabled !== true
        );
      }
      updateStatePersistenceUsageDisplay();
      if (saveStateNowBtn) {
        saveStateNowBtn.disabled = state.statePersistenceEnabled !== true;
      }
      if (state.statePersistenceEnabled === true) {
        setSaveStateNowStatus("No manual snapshot run yet.");
      } else {
        setSaveStateNowStatus(
          "State persistence is disabled in provider settings.",
          "error"
        );
      }
      setActiveSettingsTab("server");
      globalSettingsModal.classList.add("open");
    }

    function closeGlobalSettingsModal() {
      hideHelpPopover();
      globalSettingsModal.classList.remove("open");
    }

    function updateStatePersistenceUsageDisplay() {
      if (stateSnapshotFileCountOutput) {
        stateSnapshotFileCountOutput.textContent = (
          `current number of stored states is ${state.stateSnapshotFileCount}`
        );
      }
    }

    function setSaveStateNowStatus(message, tone = "") {
      if (!saveStateNowStatus) return;
      saveStateNowStatus.textContent = String(message || "");
      saveStateNowStatus.classList.remove("success", "error");
      if (tone === "success" || tone === "error") {
        saveStateNowStatus.classList.add(tone);
      }
    }

    async function saveStateNowFromSettings() {
      if (!saveStateNowBtn) return;
      saveStateNowBtn.disabled = true;
      const originalLabel = saveStateNowBtn.textContent;
      saveStateNowBtn.textContent = "Saving...";
      setSaveStateNowStatus("Saving snapshot...");
      try {
        const resp = await apiFetch("/api/settings/state/save", {
          method: "POST",
        });
        const payload = await resp.json().catch(() => ({}));
        if (!resp.ok) {
          const errorMessage = String(
            payload && payload.error
              ? payload.error
              : "Failed to save provider state snapshot."
          );
          setSaveStateNowStatus(errorMessage, "error");
          return;
        }
        const snapshotPath = String(payload.snapshot_path || "").trim();
        await fetchSettings();
        updateStatePersistenceUsageDisplay();
        if (snapshotPath) {
          const snapshotName = snapshotPath.split(/[\\/]/).pop() || snapshotPath;
          setSaveStateNowStatus(`Created: ${snapshotName}`, "success");
          return;
        }
        setSaveStateNowStatus("Snapshot saved.", "success");
      } catch (_error) {
        setSaveStateNowStatus(
          "Failed to save provider state snapshot.",
          "error"
        );
      } finally {
        saveStateNowBtn.disabled = false;
        saveStateNowBtn.textContent = originalLabel;
      }
    }

    function resetPendingApprovalDecisions() {
      pendingApprovalDecisions = {};
      state.pendingApprovals.forEach(client => {
        if (!client || !client.client_id) return;
        pendingApprovalDecisions[String(client.client_id)] = "block";
      });
    }

    function pendingApprovalDetails(client) {
      const agentDesc = client && client.agent_description ? String(client.agent_description) : "";
      const instanceId = extractAgentField(agentDesc, "service.instance.id") || "--";
      const serviceName = extractAgentField(agentDesc, "service.name") || "--";
      const hostType = extractAgentField(agentDesc, "os_type") || "--";
      const clientVersion = client && client.client_version ? String(client.client_version) : "--";
      const ipAddress = client && client.remote_addr ? String(client.remote_addr) : "--";
      return {
        uid: client && client.client_id ? String(client.client_id) : "--",
        instanceId,
        ipAddress,
        agentTypeVersion: `${serviceName} / ${clientVersion}`,
        hostType,
      };
    }

    function renderPendingApprovalTable() {
      if (!Array.isArray(state.pendingApprovals) || state.pendingApprovals.length === 0) {
        pendingApprovalBody.innerHTML = '<tr><td colspan="6" class="approval-empty">No pending approvals.</td></tr>';
        return;
      }
      pendingApprovalBody.innerHTML = "";
      state.pendingApprovals.forEach((client, index) => {
        if (!client || !client.client_id) return;
        const details = pendingApprovalDetails(client);
        const decisionValue = pendingApprovalDecisions[details.uid] || "block";
        const rowToggleId = `pending-approval-${index}-${details.uid.replace(/[^A-Za-z0-9_-]/g, "_")}`;
        const row = document.createElement("tr");
        row.innerHTML = `
          <td>${details.uid}</td>
          <td>${details.instanceId}</td>
          <td>${details.ipAddress}</td>
          <td>${details.agentTypeVersion}</td>
          <td>${details.hostType}</td>
          <td>
            <label class="approval-toggle" for="${rowToggleId}">
              <input
                id="${rowToggleId}"
                type="checkbox"
                class="approval-toggle-input"
                data-pending-client-id="${details.uid}"
                aria-label="Pending approval decision for ${details.uid}"
              />
              <span class="approval-toggle-track" aria-hidden="true"></span>
              <span class="approval-toggle-state"></span>
            </label>
          </td>
        `;
        const toggle = row.querySelector("input[data-pending-client-id]");
        const stateLabel = row.querySelector(".approval-toggle-state");
        const applyDecision = decision => {
          const normalized = String(decision || "").toLowerCase() === "approve" ? "approve" : "block";
          pendingApprovalDecisions[details.uid] = normalized;
          if (toggle) {
            toggle.checked = normalized === "approve";
          }
          if (stateLabel) {
            stateLabel.textContent = normalized === "approve" ? "Accept" : "Block";
          }
        };
        if (toggle) {
          applyDecision(decisionValue);
          toggle.addEventListener("change", () => {
            applyDecision(toggle.checked ? "approve" : "block");
          });
        }
        pendingApprovalBody.appendChild(row);
      });
    }

    function setAllPendingApprovals(decision) {
      const normalized = String(decision || "").toLowerCase() === "approve" ? "approve" : "block";
      state.pendingApprovals.forEach(client => {
        if (!client || !client.client_id) return;
        pendingApprovalDecisions[String(client.client_id)] = normalized;
      });
      pendingApprovalBody.querySelectorAll("input[data-pending-client-id]").forEach(toggle => {
        toggle.checked = normalized === "approve";
        toggle.dispatchEvent(new Event("change"));
      });
    }

    async function openPendingApprovalModal() {
      if (state.humanInLoopApproval !== true) {
        return;
      }
      await fetchPendingApprovals();
      resetPendingApprovalDecisions();
      renderPendingApprovalTable();
      pendingApprovalModal.classList.add("open");
    }

    function closePendingApprovalModal() {
      pendingApprovalModal.classList.remove("open");
    }

    async function savePendingApprovalDecisions() {
      if (!Array.isArray(state.pendingApprovals) || state.pendingApprovals.length === 0) {
        closePendingApprovalModal();
        return;
      }
      const decisions = state.pendingApprovals
        .filter(client => client && client.client_id)
        .map(client => ({
          client_id: String(client.client_id),
          decision: pendingApprovalDecisions[String(client.client_id)] === "approve"
            ? "approve"
            : "block",
        }));
      const resp = await apiFetch("/api/approvals/pending", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decisions }),
      });
      if (!resp.ok) {
        window.alert("Failed to apply pending approval decisions.");
        return;
      }
      closePendingApprovalModal();
      await fetchPendingApprovals();
      await fetchClients();
    }

    async function saveGlobalSettings() {
      const proposedDelayed = parseInt(delayedCommsSecondsInput.value, 10);
      const proposedSignificant = parseInt(significantCommsSecondsInput.value, 10);
      const proposedClientEventHistorySize = parseInt(
        clientEventHistorySizeInput.value,
        10
      );
      const proposedStateSaveFolder = String(stateSaveFolderInput.value || "").trim();
      const proposedRetentionCount = parseInt(retentionCountInput.value, 10);
      const proposedAutosaveInterval = parseInt(autosaveIntervalInput.value, 10);
      const proposedHumanInLoopApproval = humanInLoopApprovalInput.checked === true;
      const proposedValue = parseInt(defaultHeartbeatFrequencyInput.value, 10);
      if (Number.isNaN(proposedDelayed) || proposedDelayed <= 0) {
        window.alert("delayed_comms_seconds must be a positive integer.");
        return;
      }
      if (Number.isNaN(proposedSignificant) || proposedSignificant <= 0) {
        window.alert("significant_comms_seconds must be a positive integer.");
        return;
      }
      if (proposedDelayed >= proposedSignificant) {
        window.alert("significant_comms_seconds must be greater than delayed_comms_seconds.");
        return;
      }
      if (
        Number.isNaN(proposedClientEventHistorySize)
        || proposedClientEventHistorySize <= 0
      ) {
        window.alert("client_event_history_size must be a positive integer.");
        return;
      }
      if (!proposedStateSaveFolder) {
        window.alert("state_save_folder must be provided.");
        return;
      }
      if (Number.isNaN(proposedRetentionCount) || proposedRetentionCount <= 0) {
        window.alert("retention_count must be a positive integer.");
        return;
      }
      if (Number.isNaN(proposedAutosaveInterval) || proposedAutosaveInterval <= 0) {
        window.alert("autosave_interval_seconds_since_change must be a positive integer.");
        return;
      }
      if (Number.isNaN(proposedValue) || proposedValue <= 0) {
        window.alert("Default Heartbeat Frequency must be a positive integer.");
        return;
      }
      if (
        proposedDelayed !== state.delayed
        || proposedSignificant !== state.significant
        || proposedClientEventHistorySize !== state.clientEventHistorySize
        || proposedStateSaveFolder !== state.stateSaveFolder
        || proposedRetentionCount !== state.retentionCount
        || proposedAutosaveInterval !== state.autosaveIntervalSecondsSinceChange
        || proposedHumanInLoopApproval !== state.humanInLoopApproval
      ) {
        const commsResp = await apiFetch("/api/settings/comms", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            delayed_comms_seconds: proposedDelayed,
            significant_comms_seconds: proposedSignificant,
            client_event_history_size: proposedClientEventHistorySize,
            human_in_loop_approval: proposedHumanInLoopApproval,
            state_save_folder: proposedStateSaveFolder,
            retention_count: proposedRetentionCount,
            autosave_interval_seconds_since_change: proposedAutosaveInterval,
          }),
        });
        if (!commsResp.ok) {
          window.alert("Failed to update server communication settings.");
          return;
        }
        const commsPayload = await commsResp.json();
        state.delayed = parseInt(commsPayload.delayed_comms_seconds, 10);
        state.significant = parseInt(commsPayload.significant_comms_seconds, 10);
        state.clientEventHistorySize = parseInt(commsPayload.client_event_history_size, 10);
        state.stateSaveFolder = String(commsPayload.state_save_folder || proposedStateSaveFolder);
        const updatedRetentionCount = parseInt(commsPayload.retention_count, 10);
        state.retentionCount = Number.isNaN(updatedRetentionCount) || updatedRetentionCount <= 0
          ? proposedRetentionCount
          : updatedRetentionCount;
        const updatedSnapshotCount = parseInt(
          commsPayload.state_snapshot_file_count,
          10
        );
        state.stateSnapshotFileCount = Number.isNaN(updatedSnapshotCount)
          || updatedSnapshotCount < 0
          ? state.stateSnapshotFileCount
          : updatedSnapshotCount;
        state.autosaveIntervalSecondsSinceChange = parseInt(
          commsPayload.autosave_interval_seconds_since_change,
          10
        );
        state.humanInLoopApproval = commsPayload.human_in_loop_approval === true;
        updatePendingApprovalVisibility();
      }
      if (proposedValue !== state.defaultHeartbeatFrequency) {
        const resp = await apiFetch("/api/settings/client", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ default_heartbeat_frequency: proposedValue }),
        });
        if (!resp.ok) {
          window.alert("Failed to update global client settings.");
          return;
        }
        const payload = await resp.json();
        const updatedFrequency = parseInt(payload.default_heartbeat_frequency, 10);
        if (!Number.isNaN(updatedFrequency) && updatedFrequency > 0) {
          state.defaultHeartbeatFrequency = updatedFrequency;
        }
      }
      closeGlobalSettingsModal();
      await fetchClients();
    }

    async function saveServerSettings() {
      const proposedDelayed = parseInt(delayedCommsSecondsInput.value, 10);
      const proposedSignificant = parseInt(significantCommsSecondsInput.value, 10);
      const proposedClientEventHistorySize = parseInt(
        clientEventHistorySizeInput.value,
        10
      );
      const proposedStateSaveFolder = String(stateSaveFolderInput.value || "").trim();
      const proposedRetentionCount = parseInt(retentionCountInput.value, 10);
      const proposedAutosaveInterval = parseInt(autosaveIntervalInput.value, 10);
      const proposedHumanInLoopApproval = humanInLoopApprovalInput.checked === true;
      if (Number.isNaN(proposedDelayed) || proposedDelayed <= 0) {
        window.alert("delayed_comms_seconds must be a positive integer.");
        return;
      }
      if (Number.isNaN(proposedSignificant) || proposedSignificant <= 0) {
        window.alert("significant_comms_seconds must be a positive integer.");
        return;
      }
      if (proposedDelayed >= proposedSignificant) {
        window.alert("significant_comms_seconds must be greater than delayed_comms_seconds.");
        return;
      }
      if (
        Number.isNaN(proposedClientEventHistorySize)
        || proposedClientEventHistorySize <= 0
      ) {
        window.alert("client_event_history_size must be a positive integer.");
        return;
      }
      if (!proposedStateSaveFolder) {
        window.alert("state_save_folder must be provided.");
        return;
      }
      if (Number.isNaN(proposedRetentionCount) || proposedRetentionCount <= 0) {
        window.alert("retention_count must be a positive integer.");
        return;
      }
      if (Number.isNaN(proposedAutosaveInterval) || proposedAutosaveInterval <= 0) {
        window.alert("autosave_interval_seconds_since_change must be a positive integer.");
        return;
      }

      const commsResp = await apiFetch("/api/settings/comms", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          delayed_comms_seconds: proposedDelayed,
          significant_comms_seconds: proposedSignificant,
          client_event_history_size: proposedClientEventHistorySize,
          human_in_loop_approval: proposedHumanInLoopApproval,
          state_save_folder: proposedStateSaveFolder,
          retention_count: proposedRetentionCount,
          autosave_interval_seconds_since_change: proposedAutosaveInterval,
        }),
      });
      if (!commsResp.ok) {
        window.alert("Failed to update server communication settings.");
        return;
      }
      const commsPayload = await commsResp.json();
      state.delayed = parseInt(commsPayload.delayed_comms_seconds, 10);
      state.significant = parseInt(commsPayload.significant_comms_seconds, 10);
      state.clientEventHistorySize = parseInt(commsPayload.client_event_history_size, 10);
      state.stateSaveFolder = String(commsPayload.state_save_folder || proposedStateSaveFolder);
      const updatedRetentionCount = parseInt(commsPayload.retention_count, 10);
      state.retentionCount = Number.isNaN(updatedRetentionCount) || updatedRetentionCount <= 0
        ? proposedRetentionCount
        : updatedRetentionCount;
      const updatedSnapshotCount = parseInt(
        commsPayload.state_snapshot_file_count,
        10
      );
      state.stateSnapshotFileCount = Number.isNaN(updatedSnapshotCount)
        || updatedSnapshotCount < 0
        ? state.stateSnapshotFileCount
        : updatedSnapshotCount;
      state.autosaveIntervalSecondsSinceChange = parseInt(
        commsPayload.autosave_interval_seconds_since_change,
        10
      );
      state.humanInLoopApproval = commsPayload.human_in_loop_approval === true;
      updatePendingApprovalVisibility();

      closeGlobalSettingsModal();
      await fetchClients();
    }

    function formatConfigValue(value) {
      if (value === null || value === undefined) return "";
      if (typeof value === "string") return value;
      if (typeof value === "object") {
        try {
          return JSON.stringify(value, null, 2);
        } catch (err) {
          return String(value);
        }
      }
      return String(value);
    }

    function renderCommandButtons(client, customCommandState = null) {
      commandButtons.innerHTML = "";
      COMMAND_OPTIONS.forEach(option => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "command-btn";
        btn.innerHTML = `<span>${option.label}</span><small>${option.description}</small>`;
        btn.addEventListener("click", () => queueCommand(option.value, client));
        commandButtons.appendChild(btn);
      });
      clientHeartbeatFrequencyInput.value = String(client.heartbeat_frequency ?? 30);
      renderCustomCommandSelect(customCommandState);
    }

    function renderCustomCommandSelect(customCommandState = null) {
      customCommandSelect.innerHTML = "";
      const defaultOption = document.createElement("option");
      defaultOption.value = "";
      defaultOption.textContent = "Select custom command...";
      customCommandSelect.appendChild(defaultOption);

      state.customCommands.forEach(command => {
        const option = document.createElement("option");
        option.value = command.fqdn || "";
        option.textContent = command.displayname || command.operation || command.fqdn || "--";
        if (command.reported_by_client === true) {
          option.style.color = "var(--ok)";
          option.style.fontWeight = "600";
        }
        customCommandSelect.appendChild(option);
      });

      const restoreFqdn =
        customCommandState
        && typeof customCommandState.selectedFqdn === "string"
        && state.customCommands.some(cmd => cmd.fqdn === customCommandState.selectedFqdn)
          ? customCommandState.selectedFqdn
          : "";
      customCommandSelect.value = restoreFqdn;
      updateCustomCommandSelectStyle();
      renderCustomCommandConfiguration(
        restoreFqdn,
        customCommandState ? customCommandState.values : null,
      );
    }

    function updateCustomCommandSelectStyle() {
      const selectedMeta = getSelectedCustomCommandMeta(customCommandSelect.value);
      if (selectedMeta && selectedMeta.reported_by_client === true) {
        customCommandSelect.style.color = "var(--ok)";
        customCommandSelect.style.fontWeight = "600";
        return;
      }
      customCommandSelect.style.color = "";
      customCommandSelect.style.fontWeight = "";
    }

    function getSelectedCustomCommandMeta(selectedFqdn) {
      return state.customCommands.find(cmd => cmd.fqdn === selectedFqdn) || null;
    }

    function toSchemaTooltip(schemaEntry, currentValue) {
      const description = String(schemaEntry.description ?? "").trim();
      return description || "No description provided.";
    }

    function isSchemaRequired(schemaEntry) {
      return schemaEntry.isRequired === true || schemaEntry.isrequired === true;
    }

    function hasMissingRequiredCustomCommandValues(selectedMeta) {
      if (!selectedMeta) return true;
      const schema = Array.isArray(selectedMeta.schema) ? selectedMeta.schema : [];
      for (const schemaEntry of schema) {
        const paramName = String(schemaEntry.parametername || "").trim();
        if (!paramName || !isSchemaRequired(schemaEntry)) continue;
        const input = Array.from(customCommandConfigBody.querySelectorAll("input")).find(
          item => item.dataset.parameter === paramName
        );
        const value = input ? String(input.value || "").trim() : "";
        if (!value) return true;
      }
      return false;
    }

    function updateCustomCommandActionAvailability() {
      const selectedMeta = getSelectedCustomCommandMeta(customCommandSelect.value);
      const canIssue = Boolean(selectedMeta) && !hasMissingRequiredCustomCommandValues(selectedMeta);
      sendCustomCommandBtn.disabled = !canIssue;
      sendCustomCommandBtn.title = canIssue
        ? "Configure and queue this command"
        : "Populate all required parameters before issuing this command";
    }

    function buildConfigValueCell(paramName, selectedMeta, overrideValue = null) {
      const input = document.createElement("input");
      input.type = "text";
      input.dataset.parameter = paramName;
      input.style.width = "100%";
      if (typeof overrideValue === "string") {
        input.value = overrideValue;
      } else {
        input.value = "";
      }
      return input;
    }

    function renderCustomCommandConfiguration(selectedFqdn, valueOverrides = null) {
      customCommandConfigBody.innerHTML = "";
      const selectedMeta = getSelectedCustomCommandMeta(selectedFqdn);
      if (!selectedMeta) {
        customCommandConfigPanel.classList.add("hidden");
        updateCustomCommandActionAvailability();
        return;
      }
      customCommandConfigPanel.classList.remove("hidden");
      const schema = Array.isArray(selectedMeta.schema) ? selectedMeta.schema : [];
      schema.forEach(schemaEntry => {
        const paramName = String(schemaEntry.parametername || "").trim();
        if (!paramName) return;
        const row = document.createElement("tr");

        const labelCell = document.createElement("td");
        const label = document.createElement("label");
        label.textContent = paramName;
        labelCell.appendChild(label);

        const valueCell = document.createElement("td");
        const overrideValue =
          valueOverrides && Object.prototype.hasOwnProperty.call(valueOverrides, paramName)
            ? String(valueOverrides[paramName] ?? "")
            : null;
        const input = buildConfigValueCell(paramName, selectedMeta, overrideValue);
        valueCell.appendChild(input);

        const infoCell = document.createElement("td");
        const info = document.createElement("span");
        info.className = "schema-icon";
        info.textContent = "i";
        info.title = toSchemaTooltip(schemaEntry, input.value);
        input.addEventListener("input", () => {
          info.title = toSchemaTooltip(schemaEntry, input.value);
          updateCustomCommandActionAvailability();
        });
        infoCell.appendChild(info);

        row.appendChild(labelCell);
        row.appendChild(valueCell);
        row.appendChild(infoCell);
        customCommandConfigBody.appendChild(row);
      });
      updateCustomCommandActionAvailability();
    }

    function captureCustomCommandState() {
      const selectedFqdn = customCommandSelect.value || "";
      const values = {};
      Array.from(customCommandConfigBody.querySelectorAll("input")).forEach(input => {
        const paramName = input.dataset.parameter;
        if (!paramName) return;
        values[paramName] = String(input.value || "");
      });
      return { selectedFqdn, values };
    }

    function renderEventsHistory(client) {
      const events = Array.isArray(client.events) ? client.events : [];
      const flattened = [];
      events.forEach(eventObj => {
        if (!eventObj || typeof eventObj !== "object") return;
        if ("event_time" in eventObj || "event_description" in eventObj) {
          const eventTime = String(eventObj.event_time || "");
          let description = String(eventObj.event_description || "").trim();
          if (!description && ("classifier" in eventObj || "action" in eventObj)) {
            const classifier = String(eventObj.classifier || "command").trim();
            const action = String(eventObj.action || eventObj.command || "unknown").trim();
            description = `${classifier} ${action}`.trim();
          }
          flattened.push({
            eventTime,
            description: description || "--",
            ts: new Date(eventTime).getTime(),
          });
          return;
        }
        Object.entries(eventObj).forEach(([eventTime, description]) => {
          flattened.push({
            eventTime,
            description: String(description),
            ts: new Date(eventTime).getTime(),
          });
        });
      });

      if (flattened.length === 0) {
        eventsHistoryList.innerHTML = `
          <tr>
            <td>--</td>
            <td>No event history yet.</td>
          </tr>
        `;
        historyTabBtn.classList.add("hidden");
        if (tabPanels.history.classList.contains("active")) {
          setActiveTab("summary");
        }
        return;
      }

      flattened.sort((a, b) => {
        const aTs = Number.isNaN(a.ts) ? 0 : a.ts;
        const bTs = Number.isNaN(b.ts) ? 0 : b.ts;
        return state.eventsSortDir === "asc" ? aTs - bTs : bTs - aTs;
      });

      eventsHistoryList.innerHTML = "";
      flattened.forEach(event => {
        const row = document.createElement("tr");
        const when = Number.isNaN(event.ts)
          ? event.eventTime
          : new Date(event.eventTime).toLocaleString();
        row.innerHTML = `
          <td>${when}</td>
          <td>${event.description}</td>
        `;
        eventsHistoryList.appendChild(row);
      });
      historyTabBtn.classList.remove("hidden");
    }

    async function queueCommand(command, client) {
      const target = client || activeClient;
      if (!target) return;
      if (command === "issue_unique_id") {
        const preservedCustomCommandState = captureCustomCommandState();
        await requestNewUniqueId(target, {
          preserveTab: true,
          customCommandState: preservedCustomCommandState,
          reopenModal: true,
          closeContextMenu: false,
        });
        return;
      }
      const ok = window.confirm(`Queue command "${command}" for client ${target.client_id}?`);
      if (!ok) return;
      const resp = await apiFetch(`/api/clients/${target.client_id}/commands`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          pairs: [
            { key: "classifier", value: "command" },
            { key: "action", value: command },
            { key: "source", value: "ui" },
            { key: "requested_at", value: new Date().toISOString() },
          ],
        }),
      });
      if (!resp.ok) {
        window.alert("Failed to queue command.");
        return;
      }
      await fetchClients();
      const refreshed = state.clients.find(
        clientEntry => clientEntry.client_id === target.client_id
      );
      if (refreshed) openModal(refreshed);
    }

    async function queueCustomCommand() {
      const target = activeClient;
      if (!target) return;
      const preservedCustomCommandState = captureCustomCommandState();
      const selectedFqdn = customCommandSelect.value;
      const selectedMeta = getSelectedCustomCommandMeta(selectedFqdn);
      if (!selectedMeta) {
        window.alert("Please select a custom command.");
        return;
      }
      if (hasMissingRequiredCustomCommandValues(selectedMeta)) {
        window.alert("Populate all required parameters before issuing this command.");
        updateCustomCommandActionAvailability();
        return;
      }

      const pairs = [];
      const schema = Array.isArray(selectedMeta.schema) ? selectedMeta.schema : [];
      let missingRequired = null;
      const configuredValues = preservedCustomCommandState.values || {};
      schema.forEach(schemaEntry => {
        const paramName = String(schemaEntry.parametername || "").trim();
        if (!paramName) return;
        const value = String(configuredValues[paramName] || "").trim();
        if (isSchemaRequired(schemaEntry) && !value && !missingRequired) {
          missingRequired = paramName;
        }
      });
      Object.entries(configuredValues).forEach(([key, rawValue]) => {
        const paramName = String(key || "").trim();
        const value = String(rawValue || "").trim();
        if (!paramName || !value) return;
        pairs.push({ key: paramName, value });
      });
      if (missingRequired) {
        window.alert(`Missing required parameter: ${missingRequired}`);
        return;
      }

      pairs.push({ key: "classifier", value: "custom" });
      pairs.push({ key: "operation", value: selectedMeta.operation || "" });
      pairs.push({ key: "capability", value: selectedMeta.fqdn || "" });

      pairs.push({ key: "source", value: "ui" });
      pairs.push({ key: "requested_at", value: new Date().toISOString() });

      const ok = window.confirm(
        `Queue custom command "${selectedMeta.displayname}" for client ${target.client_id}?`
      );
      if (!ok) return;

      const resp = await apiFetch(`/api/clients/${target.client_id}/commands`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pairs }),
      });
      if (!resp.ok) {
        window.alert("Failed to queue custom command.");
        return;
      }
      await fetchClients();
      const refreshed = state.clients.find(
        clientEntry => clientEntry.client_id === target.client_id
      );
      if (refreshed) {
        openModal(refreshed, {
          preserveTab: true,
          customCommandState: preservedCustomCommandState,
        });
      }
    }

    async function saveClientHeartbeat() {
      const target = activeClient;
      if (!target) return;
      const preservedCustomCommandState = captureCustomCommandState();
      const proposedValue = parseInt(clientHeartbeatFrequencyInput.value, 10);
      if (Number.isNaN(proposedValue) || proposedValue <= 0) {
        window.alert("Client heartbeat frequency must be a positive integer.");
        return;
      }
      const resp = await apiFetch(`/api/clients/${target.client_id}/heartbeat-frequency`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ heartbeat_frequency: proposedValue }),
      });
      if (!resp.ok) {
        window.alert("Failed to update client heartbeat frequency.");
        return;
      }
      await fetchClients();
      const refreshed = state.clients.find(
        clientEntry => clientEntry.client_id === target.client_id
      );
      if (refreshed) {
        openModal(refreshed, {
          preserveTab: true,
          customCommandState: preservedCustomCommandState,
        });
      }
    }

    async function saveConfig() {
      if (!activeClient) return;
      const configValue = configInput.value.trim();
      if (!configValue) {
        closeModal();
        return;
      }
      if (configValue) {
        await apiFetch(`/api/clients/${activeClient.client_id}/config`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ config: configValue }),
        });
      }
      closeModal();
      await fetchClients();
    }

    function extractAgentField(text, key) {
      if (!text) return "";
      const stringRegex = new RegExp(`key: \\"${key}\\"[\\s\\S]*?string_value: \\"([^\\"]*)\\"`);
      const stringMatch = text.match(stringRegex);
      if (stringMatch) return stringMatch[1];
      const bytesRegex = new RegExp(`key: \\"${key}\\"[\\s\\S]*?bytes_value: \\"([^\\"]*)\\"`);
      const bytesMatch = text.match(bytesRegex);
      if (bytesMatch) return bytesMatch[1];
      return "";
    }

    function getClientDisplayId(client) {
      const agentDesc = client && client.agent_description ? String(client.agent_description) : "";
      const serviceInstanceId = extractAgentField(agentDesc, "service.instance.id");
      if (serviceInstanceId) return serviceInstanceId;
      return client && client.client_id ? String(client.client_id) : "--";
    }

    function getClientHealthInfo(client) {
      const health = client && typeof client.health === "object" ? client.health : null;
      const healthyRaw = String((health && health.healthy) ?? "");
      let healthyLabel = "unknown";
      if (healthyRaw === "1" || healthyRaw.toLowerCase() === "true") healthyLabel = "healthy";
      if (healthyRaw === "0" || healthyRaw.toLowerCase() === "false") healthyLabel = "unhealthy";
      const summary = healthyLabel;
      const componentMap =
        client && typeof client.component_health === "object" && client.component_health
          ? client.component_health
          : health && typeof health.component_health_map === "object" && health.component_health_map
            ? health.component_health_map
            : {};
      return {
        summary,
        textClass: `health-text-${healthyLabel}`,
        componentMap,
        hasComponents: Object.keys(componentMap).length > 0,
      };
    }

    function renderComponentHealthMap(componentMap) {
      componentHealthBody.innerHTML = "";
      Object.entries(componentMap).forEach(([name, value]) => {
        const row = document.createElement("tr");
        const healthyRaw = String((value && value.healthy) ?? "");
        const healthy =
          healthyRaw === "1" || healthyRaw.toLowerCase() === "true" ? "yes"
          : healthyRaw === "0" || healthyRaw.toLowerCase() === "false" ? "no"
          : "--";
        const status = value && value.status ? String(value.status) : "--";
        const lastError = value && value.last_error ? String(value.last_error) : "--";
        if (healthy === "yes") {
          row.classList.add("health-row-ok");
        } else if (healthy === "no") {
          row.classList.add("health-row-bad");
        } else {
          row.classList.add("health-row-unknown");
        }
        row.innerHTML = `
          <td>${name}</td>
          <td>${healthy}</td>
          <td>${status}</td>
          <td>${lastError}</td>
        `;
        componentHealthBody.appendChild(row);
      });
    }

    function renderCapabilitiesList(capabilities) {
      if (!capabilities || capabilities.length === 0) return "--";
      return `<div class="cap-list">${capabilities
        .map(cap => `<span class="cap-pill">${cap}</span>`)
        .join("")}</div>`;
    }

    function computeNextExpected(client) {
      if (!client.last_communication) return null;
      const last = new Date(client.last_communication);
      if (Number.isNaN(last.getTime())) return null;
      const intervalSeconds = client.heartbeat_frequency ?? state.refreshSeconds;
      return new Date(last.getTime() + intervalSeconds * 1000).toISOString();
    }

    function hideContextMenu() {
      contextMenu.classList.remove("open");
      contextClient = null;
    }

    async function removeClient() {
      if (!contextClient) return;
      const ok = window.confirm(`Remove client ${contextClient.client_id} from the server?`);
      if (!ok) return;
      const resp = await apiFetch(`/api/clients/${contextClient.client_id}`, { method: "DELETE" });
      hideContextMenu();
      if (!resp.ok) {
        window.alert("Failed to remove client.");
        return;
      }
      await fetchClients();
    }

    async function requestNewUniqueId(target, options = {}) {
      if (!target) return;
      const ok = window.confirm(
        `Issue a new unique ID for client ${target.client_id}?`
      );
      if (!ok) return;
      const resp = await apiFetch(`/api/clients/${target.client_id}/identify`, {
        method: "POST",
      });
      if (options.closeContextMenu !== false) {
        hideContextMenu();
      }
      if (!resp.ok) {
        window.alert("Failed to issue new unique ID.");
        return;
      }
      await fetchClients();
      if (options.reopenModal !== true) return;
      const refreshed = state.clients.find(
        clientEntry => clientEntry.client_id === target.client_id
      );
      if (!refreshed) return;
      if (options.preserveTab === true) {
        openModal(refreshed, {
          preserveTab: true,
          customCommandState: options.customCommandState || null,
        });
        return;
      }
      openModal(refreshed);
    }

    async function issueNewId(event) {
      if (event) {
        event.preventDefault();
        event.stopPropagation();
      }
      if (!contextClient) return;
      const target = contextClient;
      await requestNewUniqueId(target, {
        closeContextMenu: true,
        reopenModal: false,
      });
    }

    async function requestShutdown() {
      const ok = window.confirm("Shutdown the OpAMP server? This will stop the process.");
      if (!ok) return;
      document.body.classList.add("shutdown-armed");
      shutdownButton.disabled = true;
      shutdownButton.textContent = "Shutting down...";
      try {
        const resp = await apiFetch("/api/shutdown", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ confirm: true }),
        });
        if (resp.ok) return;
      } catch (_error) {
        // Fall through to reset UI and show failure prompt.
      }
      document.body.classList.remove("shutdown-armed");
      shutdownButton.disabled = false;
      shutdownButton.textContent = "Shutdown Server";
      window.alert("Shutdown request failed.");
    }

    function scheduleRefresh() {
      if (state.timer) clearInterval(state.timer);
      state.timer = setInterval(fetchClients, state.refreshSeconds * 1000);
    }

    function loadStoredAuthToken() {
      try {
        return String(window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY) || "").trim();
      } catch (_error) {
        return "";
      }
    }

    function updateAuthTokenStatus() {
      authTokenStatus.textContent = state.authToken ? "Token: set" : "Token: not set";
    }

    function setAuthToken(token) {
      state.authToken = String(token || "").trim();
      try {
        if (state.authToken) {
          window.localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, state.authToken);
        } else {
          window.localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
        }
      } catch (_error) {
        // Ignore localStorage failures and continue with in-memory token use.
      }
      updateAuthTokenStatus();
    }

    function initializeAuthToken() {
      const storedToken = loadStoredAuthToken();
      state.authToken = storedToken;
      authTokenInput.value = storedToken;
      updateAuthTokenStatus();
    }

    async function apiFetch(resource, options = {}) {
      const fetchOptions = { ...options };
      const headers = {
        ...(options.headers || {}),
      };
      if (state.authToken) {
        headers.Authorization = `Bearer ${state.authToken}`;
      }
      fetchOptions.headers = headers;
      return fetch(resource, fetchOptions);
    }

    async function init() {
      initializeAuthToken();
      setClientFilterState(state.filters);
      writeClientFiltersToInputs();
      updateActiveFiltersIndicator();
      await fetchGlobalSettingsHelp();
      await fetchSettings();
      await fetchClientSettings();
      await fetchCustomCommands();
      await fetchPendingApprovals();
      await fetchClients();
      scheduleRefresh();
    }
