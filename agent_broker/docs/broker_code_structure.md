# Broker Code Structure Diagrams

This page provides a code-oriented view of how `opamp_broker` modules fit
together at startup and at request-processing time.

## 1) Module/package overview

```mermaid
flowchart LR
    subgraph Runtime["Runtime Orchestration"]
        BrokerApp["broker_app.py"]
        ConfigLoader["config/loader.py"]
        SocialFactory["social_collaboration/factory.py"]
        SessionManager["session/manager.py"]
        SessionSweeper["session/sweeper.py"]
    end

    subgraph Collaboration["Social Collaboration"]
        SocialBase["social_collaboration/base.py"]
        SocialSlack["social_collaboration/slack.py"]
        SlackClient["slack/client.py"]
        SlackHandlers["slack/handlers.py"]
    end

    subgraph Planning["Conversation Planning + Execution"]
        GraphBuilder["graph/graph.py"]
        GraphNodes["graph/nodes.py"]
        PlannerFactory["planner/factory.py"]
        RulePlanner["planner/rule_first_planner.py"]
        AISvcPlanner["planner/ai_svc_planner.py"]
        AIConnFactory["planner/ai_connection_factory.py"]
        OpenAIConn["planner/openai_compatible_connection.py"]
    end

    subgraph MCP["MCP Integration"]
        MCPClient["mcp/client.py"]
        MCPRegistry["mcp/tools.py"]
    end

    BrokerApp --> ConfigLoader
    BrokerApp --> SocialFactory
    BrokerApp --> SessionManager
    BrokerApp --> SessionSweeper
    BrokerApp --> MCPClient
    BrokerApp --> MCPRegistry
    BrokerApp --> GraphBuilder

    SocialFactory --> SocialBase
    SocialFactory --> SocialSlack
    SocialSlack --> SlackClient
    SocialSlack --> SlackHandlers
    SlackHandlers --> GraphBuilder
    SlackHandlers --> SessionManager

    GraphBuilder --> GraphNodes
    GraphBuilder --> PlannerFactory
    GraphNodes --> MCPRegistry
    GraphNodes --> RulePlanner
    PlannerFactory --> RulePlanner
    PlannerFactory --> AISvcPlanner
    PlannerFactory --> AIConnFactory
    AIConnFactory --> OpenAIConn
    AISvcPlanner --> OpenAIConn
    MCPRegistry --> MCPClient
```

![Broker code structure overview](./broker_code_structure_overview.png)

## 2) Startup wiring flow

```mermaid
flowchart TD
    Start["python -m opamp_broker.broker_app"] --> LoadEnv["load_dotenv()"]
    LoadEnv --> LoadConfig["load_runtime_config()"]
    LoadConfig --> ConfigureLogging["configure_logging()"]
    ConfigureLogging --> ResolveAdapter["resolve social collaboration impl"]
    ResolveAdapter --> ResolveMCP["resolve MCP connection settings"]

    ResolveMCP --> VerifyMode{"--verify-startup?"}
    VerifyMode -- "yes" --> VerifySocial["verify social adapter connection"]
    VerifyMode -- "yes" --> VerifyAI["verify AI service connection"]
    VerifySocial --> ExitVerify["exit with verification result"]
    VerifyAI --> ExitVerify

    VerifyMode -- "no" --> CreateMCP["create MCPClient"]
    CreateMCP --> CreateRegistry["create MCPToolRegistry"]
    CreateRegistry --> RefreshTools["startup tool refresh with backoff"]
    RefreshTools --> BuildGraph["build_graph(tool_registry, config)"]
    BuildGraph --> CreateSessions["create SessionManager + SessionSweeper"]
    CreateSessions --> CreateSocial["create social adapter"]
    CreateSocial --> RegisterHandlers["register Slack handlers"]
    RegisterHandlers --> StartTasks["start sweeper + social adapter tasks"]
    StartTasks --> WaitSignal["wait for SIGINT/SIGTERM"]
    WaitSignal --> Shutdown["shutdown(): goodbye + close MCP + cancel tasks"]
```

![Broker startup wiring](./broker_startup_wiring.png)

## 3) Request-processing flow

```mermaid
sequenceDiagram
    participant U as Slack User
    participant H as slack/handlers.py
    participant S as session/manager.py
    participant G as graph/graph.py
    participant N as graph/nodes.py
    participant P as planner/*
    participant R as mcp/tools.py
    participant C as mcp/client.py
    participant M as OpAMP MCP Server

    U->>H: Message / slash command
    H->>S: upsert(thread session)
    H->>G: compiled_graph.ainvoke(state)
    G->>N: normalize_input
    G->>N: classify_intent
    G->>N: plan_action
    N->>R: list_names() / refresh() if empty
    N->>P: planner.plan(text, tools)
    P-->>N: plan {tool_name, tool_args, response_text}
    alt tool selected
        G->>N: execute_or_summarize
        N->>R: call_tool(name, args)
        R->>C: tools/call JSON-RPC
        C->>M: POST /mcp
        M-->>C: tool result payload
        C-->>R: parsed result
        R-->>N: result
        N-->>G: plain-English response_text
    else no tool selected
        N-->>G: direct response_text
    end
    G-->>H: final state
    H->>S: update session summary/intent
    H-->>U: thread reply
```

![Broker request processing](./broker_request_processing.png)
