    const state = {
      clients: [],
      pendingApprovals: [],
      customCommands: [],
      eventsSortDir: "desc",
      sortKey: "client_id",
      sortDir: "asc",
      page: 1,
      pageSize: 20,
      refreshSeconds: 30,
      delayed: 60,
      significant: 300,
      minutesKeepDisconnected: 30,
      clientEventHistorySize: 50,
      stateSaveFolder: "runtime",
      retentionCount: 5,
      stateSnapshotFileCount: 0,
      autosaveIntervalSecondsSinceChange: 600,
      defaultHeartbeatFrequency: 30,
      diagnosticEnabled: false,
      statePersistenceEnabled: false,
      humanInLoopApproval: false,
      opampUseAuthorization: "none",
      tlsEnabled: false,
      httpsCertificateExpiryDate: null,
      httpsCertificateDaysRemaining: null,
      httpsCertificateExpiringSoon: false,
      authToken: "",
      timer: null,
    };

    const clientBody = document.getElementById("clientBody");
    const lastUpdated = document.getElementById("lastUpdated");
    const agentCount = document.getElementById("agentCount");
    const amberCount = document.getElementById("amberCount");
    const redCount = document.getElementById("redCount");
    const pendingApprovalPill = document.getElementById("pendingApprovalPill");
    const pendingApprovalCount = document.getElementById("pendingApprovalCount");
    const pageNum = document.getElementById("pageNum");
    const pageTotal = document.getElementById("pageTotal");
    const pageJump = document.getElementById("pageJump");
    const refreshInput = document.getElementById("refreshInput");
    const pageSizeInput = document.getElementById("pageSizeInput");
    const authTokenInput = document.getElementById("authTokenInput");
    const applyAuthTokenBtn = document.getElementById("applyAuthTokenBtn");
    const clearAuthTokenBtn = document.getElementById("clearAuthTokenBtn");
    const authTokenStatus = document.getElementById("authTokenStatus");
    const authTokenGroup = document.getElementById("authTokenGroup");
    const modal = document.getElementById("modal");
    const modalCard = document.getElementById("modalCard");
    const modalFields = document.getElementById("modalFields");
    const modalTitle = document.getElementById("modalTitle");
    const configInput = document.getElementById("configInput");
    const currentConfigOutput = document.getElementById("currentConfigOutput");
    const componentHealthPanel = document.getElementById("componentHealthPanel");
    const componentHealthBody = document.getElementById("componentHealthBody");
    const hideHealthDataBtn = document.getElementById("hideHealthDataBtn");
    const clientDataPanel = document.getElementById("clientDataPanel");
    const clientDataYaml = document.getElementById("clientDataYaml");
    const hideClientDataBtn = document.getElementById("hideClientDataBtn");
    const toggleDataBtn = document.getElementById("toggleDataBtn");
    const commandButtons = document.getElementById("commandButtons");
    const customCommandSelect = document.getElementById("customCommandSelect");
    const customCommandConfigPanel = document.getElementById("customCommandConfigPanel");
    const customCommandConfigBody = document.getElementById("customCommandConfigBody");
    const sendCustomCommandBtn = document.getElementById("sendCustomCommandBtn");
    const clientHeartbeatFrequencyInput = document.getElementById(
      "clientHeartbeatFrequencyInput"
    );
    const setClientHeartbeatBtn = document.getElementById("setClientHeartbeatBtn");
    const saveConfigBtn = document.getElementById("saveConfigBtn");
    const historyTabBtn = document.getElementById("historyTabBtn");
    const eventsHistoryList = document.getElementById("eventsHistoryList");
    const eventsSortBtn = document.getElementById("eventsSortBtn");
    const shutdownButton = document.getElementById("shutdownButton");
    const contextMenu = document.getElementById("contextMenu");
    const removeClientBtn = document.getElementById("removeClientBtn");
    const issueIdBtn = document.getElementById("issueIdBtn");
    const globalSettingsBtn = document.getElementById("globalSettingsBtn");
    const globalSettingsModal = document.getElementById("globalSettingsModal");
    const statePersistenceGroup = document.getElementById("statePersistenceGroup");
    const closeGlobalSettingsBtn = document.getElementById("closeGlobalSettingsBtn");
    const cancelGlobalSettingsBtn = document.getElementById("cancelGlobalSettingsBtn");
    const saveGlobalSettingsBtn = document.getElementById("saveGlobalSettingsBtn");
    const saveServerSettingsBtn = document.getElementById("saveServerSettingsBtn");
    const settingsTabServerOpampConfigBtn = document.getElementById(
      "settingsTabServerOpampConfigBtn"
    );
    const defaultHeartbeatFrequencyInput = document.getElementById(
      "defaultHeartbeatFrequencyInput"
    );
    const delayedCommsSecondsInput = document.getElementById(
      "delayedCommsSecondsInput"
    );
    const significantCommsSecondsInput = document.getElementById(
      "significantCommsSecondsInput"
    );
    const minutesKeepDisconnectedInput = document.getElementById(
      "minutesKeepDisconnectedInput"
    );
    const clientEventHistorySizeInput = document.getElementById(
      "clientEventHistorySizeInput"
    );
    const humanInLoopApprovalInput = document.getElementById(
      "humanInLoopApprovalInput"
    );
    const statePersistenceEnabledInput = document.getElementById(
      "statePersistenceEnabledInput"
    );
    const stateSaveFolderInput = document.getElementById("stateSaveFolderInput");
    const retentionCountInput = document.getElementById("retentionCountInput");
    const stateSnapshotFileCountOutput = document.getElementById(
      "stateSnapshotFileCountOutput"
    );
    const autosaveIntervalInput = document.getElementById("autosaveIntervalInput");
    const saveStateNowBtn = document.getElementById("saveStateNowBtn");
    const saveStateNowStatus = document.getElementById("saveStateNowStatus");
    const delayedCommsSecondsLabel = document.getElementById(
      "delayedCommsSecondsLabel"
    );
    const significantCommsSecondsLabel = document.getElementById(
      "significantCommsSecondsLabel"
    );
    const minutesKeepDisconnectedLabel = document.getElementById(
      "minutesKeepDisconnectedLabel"
    );
    const clientEventHistorySizeLabel = document.getElementById(
      "clientEventHistorySizeLabel"
    );
    const humanInLoopApprovalLabel = document.getElementById(
      "humanInLoopApprovalLabel"
    );
    const statePersistenceEnabledLabel = document.getElementById(
      "statePersistenceEnabledLabel"
    );
    const stateSaveFolderLabel = document.getElementById("stateSaveFolderLabel");
    const retentionCountLabel = document.getElementById("retentionCountLabel");
    const autosaveIntervalLabel = document.getElementById("autosaveIntervalLabel");
    const httpsCertificateExpiryGroup = document.getElementById(
      "httpsCertificateExpiryGroup"
    );
    const httpsCertificateExpiryOutput = document.getElementById(
      "httpsCertificateExpiryOutput"
    );
    const defaultHeartbeatFrequencyLabel = document.getElementById(
      "defaultHeartbeatFrequencyLabel"
    );
    const settingsTabButtons = Array.from(
      document.querySelectorAll(".settings-tab-button")
    );
    const pendingApprovalModal = document.getElementById("pendingApprovalModal");
    const pendingApprovalBody = document.getElementById("pendingApprovalBody");
    const closePendingApprovalBtn = document.getElementById("closePendingApprovalBtn");
    const cancelPendingApprovalBtn = document.getElementById("cancelPendingApprovalBtn");
    const savePendingApprovalBtn = document.getElementById("savePendingApprovalBtn");
    const setAllApproveBtn = document.getElementById("setAllApproveBtn");
    const setAllBlockBtn = document.getElementById("setAllBlockBtn");
    const serverOpampConfigPathOutput = document.getElementById(
      "serverOpampConfigPathOutput"
    );
    const serverOpampConfigOutput = document.getElementById(
      "serverOpampConfigOutput"
    );
    const settingsTabPanels = {
      server: document.getElementById("settings-tab-server"),
      client: document.getElementById("settings-tab-client"),
      "server-opamp-config": document.getElementById("settings-tab-server-opamp-config"),
    };
    const tabButtons = Array.from(document.querySelectorAll(".tab-button"));
    const tabPanels = {
      summary: document.getElementById("tab-summary"),
      commands: document.getElementById("tab-commands"),
      config: document.getElementById("tab-config"),
      history: document.getElementById("tab-history"),
    };

    const COMMAND_OPTIONS = [
      { value: "restart", label: "Restart Agent", description: "Request a graceful restart." },
      {
        value: "forceresync",
        label: "Force Resync",
        description: "Request full state re-reporting via ReportFullState flag.",
      },
      {
        value: "issue_unique_id",
        label: "Issue New Unique ID",
        description: "Request a replacement OpAMP instance UID for this client.",
      },
    ];
    const AUTH_TOKEN_STORAGE_KEY = "opamp_ui_bearer_token";

    let activeClient = null;
    let contextClient = null;
    let pendingApprovalDecisions = {};
    let activeHelpPopover = null;
    let activeHelpIcon = null;
    const DEFAULT_GLOBAL_SETTINGS_HELP = {
      delayed_comms_seconds: {
        label: "Delayed Communications Threshold (seconds)",
        tooltip: "Seconds before a client is marked delayed (amber). This overrides the config file value.",
      },
      significant_comms_seconds: {
        label: "Significant Communications Threshold (seconds)",
        tooltip: "Seconds before a client is marked late (red). Must be greater than delayed_comms_seconds. This overrides the config file value.",
      },
      minutes_keep_disconnected: {
        label: "Disconnected Retention Window (minutes)",
        tooltip: "Minutes to keep disconnected clients in provider state before purge. This overrides the config file value.",
      },
      client_event_history_size: {
        label: "Client Event History Size",
        tooltip: "Maximum number of recent per-client events retained by the provider. Older events are dropped when this limit is exceeded.",
      },
      human_in_loop_approval: {
        label: "Human In Loop Approval",
        tooltip: "When enabled, unknown agents are staged for manual review and remain blocked until approved.",
      },
      state_persistence_enabled: {
        label: "State Persistence Enabled",
        tooltip: "When enabled, provider state snapshots can be saved/restored using state persistence settings.",
      },
      state_save_folder: {
        label: "State Save Folder",
        tooltip: "Folder used for persisted provider state snapshots.",
      },
      retention_count: {
        label: "State Snapshot Retention Count",
        tooltip: "Number of latest provider state snapshot files to retain.",
      },
      autosave_interval_seconds_since_change: {
        label: "Autosave Interval Since Change (seconds)",
        tooltip: "Seconds between autosaves after non-heartbeat OpAMP state changes.",
      },
      default_heartbeat_frequency: {
        label: "Default Heartbeat Frequency (seconds)",
        tooltip: "Default heartbeat interval in seconds applied to clients when globally updated.",
      },
    };
