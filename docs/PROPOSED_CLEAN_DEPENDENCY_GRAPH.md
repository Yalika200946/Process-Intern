# Proposed Clean Dependency Graph

## Legacy consolidation into canonical stages

```mermaid
flowchart LR
    classDef legacy fill:#eeeeee,stroke:#777,color:#333
    classDef target fill:#eaf7ea,stroke:#3d8b40,color:#153d18
    classDef src fill:#eef6ff,stroke:#3973ac,color:#16324f
    classDef review fill:#ffe8e8,stroke:#c62828,color:#641515
    classDef exp fill:#f1eaff,stroke:#7451a6,color:#2f1854

    L01["NB01 cleaning"]:::legacy --> T03["03 ingestion"]:::target
    L01 --> T04["04 data quality"]:::target
    L01 --> T06["06 crude properties"]:::target

    L02["NB02 features"]:::legacy --> T07["07 HX heat duty"]:::review
    L02 --> T08["08 clean baseline"]:::review
    L02 --> T09["09 fouling"]:::review
    L02 --> T10["10 cleaning events"]:::review

    L03["NB03 modes"]:::legacy --> T05["05 alignment/modes"]:::review
    L04["NB04 Q/rates"]:::legacy --> T07
    L04 --> T09
    L05["NB05 Q-CIT"]:::legacy --> T11["11 CIT/furnace impact"]:::review
    L06["NB06 forecast"]:::legacy --> T08
    L06 --> T12["12 forecasting"]:::review
    L07["NB07 TTC"]:::legacy --> T12
    L08["NB08 priority"]:::legacy --> T13["13 prioritization"]:::review
    L09["NB09 mixed model"]:::legacy --> T07
    L09 --> T11
    L09 --> T12
    L09 --> T13
    L10["NB10 benchmark"]:::exp --> T12
    L11["NB11 SHAP"]:::exp --> T11
    L11 --> T13
    L12["NB12 delta-CIT"]:::legacy --> T08
    L12 --> T11
    L12 --> T14["14 economics"]:::review
    L13["NB13 export"]:::legacy --> T12
    L13 --> T15["15 dashboard dataset"]:::target
    L14["NB14 TAM"]:::exp --> T08
    L14 --> T10
    L14 --> T11
    L15["NB15 audit"]:::legacy --> T16["16 validation"]:::target
    L16["NB16 plan"]:::legacy --> T13
    L16 --> T14

    SRC["Canonical src modules"]:::src --> T03
    SRC --> T04
    SRC --> T05
    SRC --> T06
    SRC --> T07
    SRC --> T08
    SRC --> T09
    SRC --> T10
    SRC --> T11
    SRC --> T12
    SRC --> T13
    SRC --> T14
    SRC --> T15
    SRC --> T16
```

## Canonical calculation ownership

```mermaid
flowchart TB
    C06["06 crude properties<br/>Cp/rho/API/SG"] --> C07["07 heat duty<br/>Q/LMTD/UA/Q_norm"]
    C07 --> C08["08 clean baseline"]
    C08 --> C09["09 fouling index/rate"]
    C09 --> C10["10 event detection"]
    C09 --> C11["11 CIT/furnace impact"]
    C10 --> C11
    C09 --> C12["12 forecasting"]
    C11 --> C12
    C10 --> C13["13 priority/schedule"]
    C11 --> C13
    C12 --> C13
    C10 --> C14["14 economic benefit"]
    C11 --> C14
    C13 --> C14
    C09 --> C15["15 approved publication"]
    C10 --> C15
    C11 --> C15
    C12 --> C15
    C13 --> C15
    C14 --> C15
    C15 --> C16["16 release validation"]
```

No calculation is owned by Stage 15 or the dashboard. Stage 15 performs presentation joins and serialization only.

## Experimental separation

```mermaid
flowchart LR
    DATA["Approved stage datasets"] --> BASE["Canonical baseline models"]
    DATA --> EXP["Experimental workspace"]
    EXP --> XGB["XGB/RF/LSTM/SHAP"]
    EXP --> PHM["GP/power/Weibull/driver SHAP"]
    EXP --> SOL["GA/DE solver comparison"]
    BASE --> GATE["Validation and engineering gate"]
    XGB -. candidate evidence .-> GATE
    PHM -. candidate evidence .-> GATE
    SOL -. candidate evidence .-> GATE
    GATE -->|"approved only"| PIPE["Canonical pipeline"]
```

## Engineering-review blockers

```mermaid
flowchart TB
    R1["E112C topology/tags"] --> BLOCK["REQUIRES_REVIEW"]
    R2["Crude property correlation vs fixed constants"] --> BLOCK
    R3["Q_norm definition"] --> BLOCK
    R4["True LMTD/UA vs proxy"] --> BLOCK
    R5["Clean-reference acceptance"] --> BLOCK
    R6["Fouling indicator/rate definition"] --> BLOCK
    R7["Cleaning-event confidence"] --> BLOCK
    R8["CIT attribution/forecast target"] --> BLOCK
    R9["Furnace limits and penalty"] --> BLOCK
    R10["Priority weights/scheduler constraints"] --> BLOCK
    R11["Economic formula/costs/additivity"] --> BLOCK
```

## Safest migration order

```mermaid
flowchart LR
    A["1. Run context + schemas"] --> B["2. Approved tag/topology snapshot"]
    B --> C["3. Immutable ingestion"]
    C --> D["4. DQ flags"]
    D --> E["5. Operating modes"]
    E --> F["6. Crude properties + heat duty shadow tables"]
    F --> G["7. Compare against legacy without publishing"]
    G --> H["8. Engineering approval"]
    H --> I["9. Continue baseline/fouling/events"]
```

