# Results

Every JSON object of a results file (`ngraph/schemas/results.json`) and what each
field means, generated from the result declarations. [How NetGraph
computes](../concepts.md#results-and-their-units) explains the numbers. They come
in five kinds:

- **Bandwidth units:** every `*_units` field and the native amounts, integers in
  units of the run's resolution `q` (the units report holds `q`); units × `q` is the
  physical amount.
- **Physical amounts:** inputs, question offers and designs, `NetworkStats`
  capacities and the units report's input samples, as declared.
- **Ratios:** delivery ratios, alpha, shares and caps, with no unit.
- **Routing costs:** path costs, tunnel costs and their sums, which never take `q`.
  `total_cost` is cost × bandwidth units, so `total_cost` × `q` is cost × physical
  bandwidth.
- **Hardware money and power:** capex and watts.

Counts are plain integers. An exact fraction is written
`{"numerator": n, "denominator": d}`. A missing key and a `null` value differ: each
field says when it is absent and when it is null. The analysis's `outputs.details`
selects which detail fields appear ([Output
selection](workflow.md#output-selection)). T1 is a `distributed_te` model; T2 is a
`centralized_te` model with a `tunnel_count`.

Placement totals and the run's `metadata` and `units_report` use the same field
names in Python and JSON. In placement and capacity rows with a native `result`,
that object and its `plan`, `by_source` and `by_tunnel` entries use the engine's
field names. There a bandwidth amount drops `_units` and a drop count ends in
`_drops`: `delivered` is `delivered_units`, `source_drops` is `source_drop_units`.
Edges and nodes are ids (`PreparedTopology.edge_refs` names each edge), so
`edge_drops` lists (edge, units) pairs, whose sum is `edge_drop_units`, and per-edge
outputs are vectors in edge order; an unlimited request or design is infinite where
JSON writes `null` with `request_kind` or `design_kind` `"unlimited"`. For placement
rows and capacity rows with a native result, `kind` is JSON only; a placement row's
`reference_shortfall_units` (`reference_request_units` minus `result.delivered`) is
also JSON only. A step's
`question` is its typed query in Python, written in normalized form here ([Results
and export](api.md#results-and-export)). Losses: [Demands: how traffic
enters](../concepts.md#demands-how-traffic-enters); the worst failure case:
[Failures: patterns, cases and
states](../concepts.md#failures-patterns-cases-and-states).

## AlphaSourceJSON

| Field | Type | Description |
| --- | --- | --- |
| `kind` | `"query"` \| `"msd_step"` | query (the query's own alpha) or msd_step. |
| `step` | string or null | The step that supplies alpha. Null when the query gives its own alpha. |

## AnalysisJSON

One of: [CapacityAnalysisJSON](#capacityanalysisjson) or [PlacementAnalysisJSON](#placementanalysisjson) or [SensitivityAnalysisJSON](#sensitivityanalysisjson) or [PathAnalysisJSON](#pathanalysisjson) or [MSDAnalysisJSON](#msdanalysisjson) or [TunnelCountAnalysisJSON](#tunnelcountanalysisjson).

## AnalysisMetadataJSON

| Field | Type | Description |
| --- | --- | --- |
| `workers` | integer | The effective number of workers. |
| `sampling` | [SamplingMetadataJSON](#samplingmetadatajson) or null | The failure sampling metadata. Null when the analysis draws no failures. |

## BuildGraphParametersJSON

| Field | Type | Description |
| --- | --- | --- |
| `add_reverse` | boolean | Whether the exported graph has a reverse edge per link. |

## BuildGraphQuestionJSON

| Field | Type | Description |
| --- | --- | --- |
| `kind` | `"build_graph"` | The record kind, a fixed tag. |
| `parameters` | [BuildGraphParametersJSON](#buildgraphparametersjson) | The step's parameters. |

## BuildGraphResultJSON

| Field | Type | Description |
| --- | --- | --- |
| `kind` | `"build_graph"` | The record kind, a fixed tag. |
| `add_reverse` | boolean | Whether the exported graph has a reverse edge per link. |
| `node_count` | integer | Nodes in the exported graph. |
| `edge_count` | integer | Edges in the exported graph (two per link with add_reverse). |
| `graph` | object | The node-link JSON of the network. |

## CapacityAnalysisJSON

| Field | Type | Description |
| --- | --- | --- |
| `kind` | `"capacity"` | The record kind, a fixed tag. |
| `metadata` | [AnalysisMetadataJSON](#analysismetadatajson) | Run or analysis metadata. |
| `outputs` | [OutputSelectionJSON](#outputselectionjson) | The output selection that applies to the rows. |
| `question` | `"lossless_bound"` \| `"fixed_offer_delivery"` \| `"first_hop_experiment"` | The question this step or analysis asked. |
| `offer_source` | `"unlimited"` \| `"explicit"` \| `"design"` \| `"first_hop"` | Where the offer comes from: unlimited, explicit, the design demand, or the first hop. |
| `cases` | list of [CapacityCaseJSON](#capacitycasejson) | The baseline case first, then each distinct failure pattern. |
| `query` | [CapacityQueryJSON](#capacityqueryjson) | The analysis's typed query (a workflow step records it as the step's question instead). Absent when the analysis is a workflow step's result. |

## CapacityCaseJSON

| Field | Type | Description |
| --- | --- | --- |
| `case` | [FailureCaseJSON](#failurecasejson) | The failure case. |
| `states` | [CapacityStatesJSON](#capacitystatesjson) | The capacity state of the case. |

## CapacityQueryJSON

| Field | Type | Description |
| --- | --- | --- |
| `kind` | `"capacity"` | The record kind, a fixed tag. |
| `source` | [SelectorJSON](#selectorjson) | The source selector. |
| `target` | [SelectorJSON](#selectorjson) | The target selector. |
| `mode` | `"combine"` \| `"pairwise"` | How sources and targets pair: combine or pairwise. |
| `model` | [ModelJSON](#modeljson) | The routing model and admission of the question. |
| `offer` | number or null | The physical offer. Null when no offer is set. |
| `design_demand` | number or null | The physical design volume of tunnels. Null when no design volume is set. |
| `failures` | [FailureRequestJSON](#failurerequestjson) or null | The failure request. Null when the question is the baseline only. |

## CapacityRowJSON

| Field | Type | Description |
| --- | --- | --- |
| `kind` | `"capacity"` | The record kind, a fixed tag. |
| `id` | string | The row's stable identifier within its analysis. |
| `endpoints` | [EndpointsJSON](#endpointsjson) | The physical source and destination node names of the row. |
| `result` | [NativePlacementJSON](#nativeplacementjson) | The native placement result. |
| `pool` | [PoolMetadataJSON](#poolmetadatajson) or null | The TE ingress pool the row's sources share. Null when the sources share no pool. |
| `cost_distribution` | [CostReportJSON](#costreportjson) | The requested cost report. Absent when the report was not requested or is not derivable. |
| `unavailable_outputs` | [UnavailableOutputsJSON](#unavailableoutputsjson) | Requested outputs that the model cannot provide, with the reason. Absent when every requested output is provided. |

## CapacityStateJSON

| Field | Type | Description |
| --- | --- | --- |
| `rows` | list of [CapacityRowJSON](#capacityrowjson) or [SelfPairJSON](#selfpairjson) | The analysis rows, one per demand or endpoint pair. |
| `totals` | null | Always null: capacity rows have no totals (each is its own question). |

## CapacityStatesJSON

| Field | Type | Description |
| --- | --- | --- |
| `converged` | [CapacityStateJSON](#capacitystatejson) | The capacity question on the case's network. |

## CostCeilingJSON

| Field | Type | Description |
| --- | --- | --- |
| `kind` | `"absolute"` \| `"stretch"` | absolute or stretch. |
| `absolute` | integer or null | The inclusive absolute cost ceiling. Null when the ceiling is a stretch. |
| `stretch` | [FractionJSON](#fractionjson) or null | The inclusive stretch over the shortest cost (a fraction). Null when the ceiling is absolute. |

## CostPowerParametersJSON

| Field | Type | Description |
| --- | --- | --- |
| `include_disabled` | boolean | Whether disabled nodes and links are counted. |
| `aggregation_level` | integer | The deepest hierarchy level reported. |

## CostPowerQuestionJSON

| Field | Type | Description |
| --- | --- | --- |
| `kind` | `"cost_power"` | The record kind, a fixed tag. |
| `parameters` | [CostPowerParametersJSON](#costpowerparametersjson) | The step's parameters. |

## CostPowerResultJSON

| Field | Type | Description |
| --- | --- | --- |
| `kind` | `"cost_power"` | The record kind, a fixed tag. |
| `include_disabled` | boolean | Whether disabled nodes and links are counted. |
| `aggregation_level` | integer | The deepest hierarchy level reported. |
| `levels` | list of [HardwareLevelJSON](#hardwareleveljson) | Hardware totals per hierarchy depth. |

## CostReportJSON

One of: [DeliveredByPathCostJSON](#deliveredbypathcostjson) or [MarginalCurveJSON](#marginalcurvejson).

## CostUnavailableReasonJSON

One of: `"mixed_cost_dag"` \| `"unsupported_model"` \| `"controller_table"`.

## CustomQuestionJSON

| Field | Type | Description |
| --- | --- | --- |
| `kind` | `"custom"` | The record kind, a fixed tag. |
| `parameters` | object | The custom step's own JSON parameters. |

## DeadCapJSON

| Field | Type | Description |
| --- | --- | --- |
| `destination` | string | The destination node name. |
| `router` | string | The router node name. |
| `forwarding_group` | string | The forwarding group (tree) name. |
| `group` | integer | The root group's index in the tree. |
| `cap` | [FractionJSON](#fractionjson) | The group's fixed cap: its share of the router's traffic (a fraction). |

## DeclaredSourceWeightJSON

| Field | Type | Description |
| --- | --- | --- |
| `source` | string | The physical source node's name. Absent when the weight is on a pool's head. |
| `pool_id` | string | The TE ingress pool whose private head carries the weight (as PoolHeadJSON names it). Absent when the weight is on a physical source. |
| `weight` | integer | Its declared weight (positive integer). |

## DeliveredByPathCostJSON

| Field | Type | Description |
| --- | --- | --- |
| `kind` | `"delivered_by_path_cost"` | The record kind, a fixed tag. |
| `cost_domain` | `"physical_network"` \| `"analysis_graph"` | physical_network, or analysis_graph when costs include the pool attachment's 1. |
| `bins` | list of [PathCostBinJSON](#pathcostbinjson) | Delivered units per path cost, in ascending cost. |

## DemandQuestionJSON

| Field | Type | Description |
| --- | --- | --- |
| `source` | [SelectorJSON](#selectorjson) | The source selector. |
| `target` | [SelectorJSON](#selectorjson) | The target selector. |
| `priority` | integer | The demand's priority (lower places first). |
| `id` | string | The declared demand's identifier. |
| `model` | [ModelJSON](#modeljson) | The routing model and admission of the question. |
| `physical_volume` | number | The declared volume in physical units. |
| `mode` | `"combine"` \| `"pairwise"` | How sources and targets pair: combine or pairwise. |
| `group_mode` | `"flatten"` \| `"per_group"` \| `"group_pairwise"` | How selector groups expand: flatten, per_group or group_pairwise. |

## DirectedLinkJSON

| Field | Type | Description |
| --- | --- | --- |
| `link` | string | The physical link identifier. |
| `direction` | `"forward"` \| `"reverse"` | The direction of the physical link: forward (source to target) or reverse. |

## DiscardedShareJSON

| Field | Type | Description |
| --- | --- | --- |
| `label` | string | The discarded expansion leaf. |
| `units` | integer | Its discarded units. |
| `reason` | `"self_pair"` \| `"filtered"` \| `"empty_selection"` | Why it was discarded: an empty selection, or an entirely excluded declaration (a self pair or identical group labels). If a declaration is excluded for both reasons, the first exclusion in canonical group and node order supplies its reason. |

## DomainQuestionJSON

One of: [BuildGraphQuestionJSON](#buildgraphquestionjson) or [NetworkStatsQuestionJSON](#networkstatsquestionjson) or [CostPowerQuestionJSON](#costpowerquestionjson).

## DomainResultJSON

One of: [BuildGraphResultJSON](#buildgraphresultjson) or [NetworkStatsResultJSON](#networkstatsresultjson) or [CostPowerResultJSON](#costpowerresultjson).

## EdgeAmountJSON

| Field | Type | Description |
| --- | --- | --- |
| `edge` | [DirectedLinkJSON](#directedlinkjson) | The directed physical link. |
| `units` | integer | The amount (integer units of q). |

## EdgeWeightJSON

| Field | Type | Description |
| --- | --- | --- |
| `edge` | [DirectedLinkJSON](#directedlinkjson) or [SyntheticIngressJSON](#syntheticingressjson) | The directed physical link, or a TE ingress pool's attachment. |
| `value` | integer | The edge's weight. |

## EndpointsJSON

| Field | Type | Description |
| --- | --- | --- |
| `sources` | list of string | Source node names, sorted. |
| `destinations` | list of string | Destination node names, sorted. |

## ExactAlphaJSON

| Field | Type | Description |
| --- | --- | --- |
| `value` | number | Alpha as a binary64 value. |
| `numerator` | integer | Alpha's exact numerator. |
| `denominator` | integer | Alpha's exact denominator. |

## ExpansionAccountingJSON

| Field | Type | Description |
| --- | --- | --- |
| `base_id` | string | The declared demand's identifier, before expansion. |
| `declared_units` | integer | The declared demand's units: its scaled total, converted to units once. |
| `resolved_units` | integer | Units split among eligible leaves, after excluding self and same-label group pairs. |
| `discarded_units` | integer | Units of its discarded leaves. |
| `discards` | list of [DiscardedShareJSON](#discardedsharejson) | Empty-selection shares, or the whole declaration when all pairs are excluded, with their reasons. |

## FailureCaseJSON

| Field | Type | Description |
| --- | --- | --- |
| `id` | string | The case identifier: baseline, or failure-NNNNNN in draw order. |
| `kind` | `"baseline"` \| `"failure"` | baseline or failure. |
| `pattern` | [FailurePatternJSON](#failurepatternjson) | The failure pattern: the failed nodes and links. |
| `occurrences` | integer | How many draws produced this pattern. |
| `trace` | [FailureTraceJSON](#failuretracejson) | The first draw's trace of this pattern. Absent when failure traces are not requested, or no draw produced the pattern. |

## FailurePatternJSON

| Field | Type | Description |
| --- | --- | --- |
| `excluded_nodes` | list of string | Failed nodes, sorted. |
| `excluded_links` | list of string | Failed links (both directions), sorted. |

## FailureRequestJSON

| Field | Type | Description |
| --- | --- | --- |
| `policy_name` | string or null | The named failure policy. Null when the policy is inline. |
| `inline_policy` | object or null | An inline failure policy. Null when the policy is named. |
| `iterations` | integer | The number of failure draws. |
| `seed` | integer or null | The draws' base seed. Null when the draws are unseeded. |
| `failure_trace` | boolean | Whether the first draw of each pattern records its trace. |

## FailureSelectionJSON

| Field | Type | Description |
| --- | --- | --- |
| `rule_index` | integer | The rule's index in its mode. |
| `scope` | `"node"` \| `"link"` \| `"risk_group"` | What the rule selects: node, link or risk_group. |
| `selected` | list of string | The selected entities. |

## FailureTraceJSON

| Field | Type | Description |
| --- | --- | --- |
| `draw_index` | integer | The draw that first produced the pattern. |
| `mode_index` | integer or null | The mode drawn. Null when the policy has no modes. |
| `mode_attrs` | object | The drawn mode's attributes. |
| `selections` | list of [FailureSelectionJSON](#failureselectionjson) | What each rule selected. |
| `expanded_nodes` | list of string | Nodes the selections expand to. |
| `expanded_links` | list of string | Links the selections expand to. |

## ForwardingFailureJSON

| Field | Type | Description |
| --- | --- | --- |
| `kind` | `"loss_iteration"` | The record kind, a fixed tag. |
| `message` | string | The native error text. |

## FractionJSON

| Field | Type | Description |
| --- | --- | --- |
| `numerator` | integer | The fraction's numerator. |
| `denominator` | integer | The fraction's denominator (positive). |

## HardwareLevelJSON

| Field | Type | Description |
| --- | --- | --- |
| `level` | integer | The hierarchy depth of the rows. |
| `rows` | list of [HardwareRowJSON](#hardwarerowjson) | One row per hierarchy path at this depth. |

## HardwareRowJSON

| Field | Type | Description |
| --- | --- | --- |
| `path` | string | The hierarchy path of the row (empty for the root level). |
| `platform_capex` | number | Platform cost of the path's nodes. |
| `platform_power_watts` | number | Platform power of the path's nodes, in watts. |
| `optics_capex` | number | Optic cost of the path's link ends. |
| `optics_power_watts` | number | Optic power of the path's link ends, in watts. |
| `capex_total` | number | Platform and optic cost. |
| `power_total_watts` | number | Platform and optic power, in watts. |

## HeadDesignJSON

| Field | Type | Description |
| --- | --- | --- |
| `head` | [SourceJSON](#sourcejson) | The tunnel head: a node name, or the pool head of a TE ingress pool. |
| `units` | integer | The head's share of the design volume (integer units of q). |

## InputConstraintJSON

| Field | Type | Description |
| --- | --- | --- |
| `kind` | `"input"` | The record kind, a fixed tag. |
| `label` | string | The input or constraint label: where the value is declared. |
| `q_upper_bound` | [FractionJSON](#fractionjson) | The largest q at which rounding this input is guaranteed within the precision: 2 times the precision times the input (rounding moves it half a unit at most). |
| `met` | boolean | Whether the chosen q meets it. |

## InputQuantizationJSON

| Field | Type | Description |
| --- | --- | --- |
| `label` | string | The input or constraint label: where the value is declared. |
| `kind` | `"capacity"` \| `"demand"` \| `"offer"` \| `"design"` \| `"min_unreserved"` | What the input is: a capacity, demand, offer, design or minimum unreserved bandwidth. |
| `binary64_value` | number | The physical input as given. |
| `binary64_hex` | string | The physical input in hexadecimal. |
| `units` | integer | Its value in units (integer units of q). |
| `error` | [FractionJSON](#fractionjson) | The signed rounding error, units times q minus the input (physical, a fraction): positive when rounded up. |
| `relative_error` | [FractionJSON](#fractionjson) or null | The signed relative error, the error divided by the input. Null when the input is zero. |

## JSONValue

One of: null or boolean or integer or number or string or list of [JSONValue](#jsonvalue) or object.

## MSDAnalysisJSON

| Field | Type | Description |
| --- | --- | --- |
| `kind` | `"msd"` | The record kind, a fixed tag. |
| `metadata` | [AnalysisMetadataJSON](#analysismetadatajson) | Run or analysis metadata. |
| `outputs` | [OutputSelectionJSON](#outputselectionjson) | The output selection of the best and probe rows. |
| `alpha_feasible` | [ExactAlphaJSON](#exactalphajson) or null | The largest tested feasible alpha. Null when no tested alpha was feasible. |
| `best_probe_index` | integer or null | The history index of the probe at alpha_feasible. Null when no tested alpha was feasible. |
| `monotone_proven` | boolean | Whether feasibility (every demand fits) is proven downward closed in alpha for this question class: an alpha below a feasible one is feasible, so the search's bracket is sound. Delivery itself need not be monotone in alpha. |
| `proof` | [MSDProofJSON](#msdproofjson) | What makes feasibility downward closed in alpha (every alpha below a feasible one is feasible). Values: fixed_program (every demand forwards a program that does not change with alpha); single_controller (one centralized-TE demand without a tunnel count, or one optimized shortest-paths demand with a static route choice, alone in its set); nothing_offered (the set offers no traffic); unproved (no proof: the search is a heuristic). |
| `upper_certificate` | [UpperCertificateJSON](#uppercertificatejson) or null | A proved bracket around the largest feasible alpha. Null when no bracket is proved. |
| `search_status` | [MSDStatusJSON](#msdstatusjson) | How the search ended. Values: feasible (the gap between a feasible and an infeasible alpha closed to alpha_tolerance); limit (a feasible alpha was found, but the search reached alpha_max or an iteration limit); none_feasible (no tested alpha was feasible); range (a probe's scaled volumes left the native range, and the search stopped there); stagnation (the next bracketing value equals the current alpha, or a bisection midpoint rounds to a bracket endpoint); trivial (the set offers no traffic and one probe at alpha_max succeeded). |
| `stop_reason` | [MSDStopReasonJSON](#msdstopreasonjson) | Why the search stopped. Values: tolerance (the gap closed to alpha_tolerance); alpha_bound (the search reached alpha_min or alpha_max); bracket_limit (max_bracket_iters ran out before a feasible and an infeasible alpha were found); bisect_limit (max_bisect_iters ran out before the gap closed); offer_range (a probe left the native range); representable_limit (the next bracketing value equals the current alpha, or a bisection midpoint rounds to a bracket endpoint); nothing_offered (the set offers no traffic); unit_resolution (no feasible alpha: each tested alpha either rounds some positive volume to zero units or does not fit). |
| `history` | list of [MSDProbeJSON](#msdprobejson) | Every probe in the order tested. |
| `best_rows` | list of [PlacementRowJSON](#placementrowjson) or null | The rows at alpha_feasible. Null when no tested alpha was feasible. |
| `best_accounting` | list of [ExpansionAccountingJSON](#expansionaccountingjson) or null | The accounting at alpha_feasible. Null when no tested alpha was feasible. |
| `probe_rows` | list of [ProbeRowsJSON](#proberowsjson) | Rows of every probe. Absent when probe rows are not requested. |
| `query` | [MSDQueryJSON](#msdqueryjson) | The analysis's typed query (a workflow step records it as the step's question instead). Absent when the analysis is a workflow step's result. |
| `controller` | list of [TableReportJSON](#tablereportjson) | The WCMP controller's tables of this demand set. Absent when no WCMP controller programs the set. |

## MSDProbeJSON

| Field | Type | Description |
| --- | --- | --- |
| `index` | integer | The probe's position in the search history (0 first). |
| `alpha` | [ExactAlphaJSON](#exactalphajson) | The probe's exact alpha. |
| `outcome` | `"feasible"` \| `"infeasible"` \| `"below_resolution"` \| `"range"` | feasible, infeasible, below_resolution (rounds to zero) or range (out of native range). |
| `totals` | [PlacementTotalsJSON](#placementtotalsjson) or null | The probe's totals. Null when the probe was out of range. |
| `range_refusal` | [RangeRefusalJSON](#rangerefusaljson) or null | Why the probe was out of range. Null when the probe was in range. |

## MSDProofJSON

One of: `"fixed_program"` \| `"single_controller"` \| `"nothing_offered"` \| `"unproved"`.

## MSDQueryJSON

| Field | Type | Description |
| --- | --- | --- |
| `kind` | `"msd"` | The record kind, a fixed tag. |
| `demand_set` | string | The demand set's name. |
| `demands` | list of [DemandQuestionJSON](#demandquestionjson) | The declared demands of the set, as they were asked. |
| `alpha_start` | number | The first alpha probed. |
| `growth_factor` | number | The factor between bracket probes. |
| `alpha_min` | number | The smallest alpha searched. |
| `alpha_max` | number | The largest alpha searched. |
| `alpha_tolerance` | number | The absolute width of the final alpha bracket at which bisection stops. |
| `max_bracket_iters` | integer | The largest number of bracket probes. |
| `max_bisect_iters` | integer | The largest number of bisection probes. |
| `export_probe_rows` | boolean | Whether every probe's rows are exported. |

## MSDStatusJSON

One of: `"feasible"` \| `"none_feasible"` \| `"range"` \| `"stagnation"` \| `"limit"` \| `"trivial"`.

## MSDStopReasonJSON

One of: `"tolerance"` \| `"alpha_bound"` \| `"bracket_limit"` \| `"bisect_limit"` \| `"offer_range"` \| `"representable_limit"` \| `"nothing_offered"` \| `"unit_resolution"`.

## MarginalCostBinJSON

| Field | Type | Description |
| --- | --- | --- |
| `marginal_cost` | integer | The increase of the minimum total cost per additional unit. |
| `units` | integer | The units delivered at that marginal cost. |

## MarginalCurveJSON

| Field | Type | Description |
| --- | --- | --- |
| `kind` | `"marginal_curve"` | The record kind, a fixed tag. |
| `cost_domain` | `"physical_network"` \| `"analysis_graph"` | physical_network, or analysis_graph when costs include the pool attachment's 1. |
| `bins` | list of [MarginalCostBinJSON](#marginalcostbinjson) | The native marginal cost curve: each piece's marginal cost and units, in ascending cost. |

## MemberWeightJSON

| Field | Type | Description |
| --- | --- | --- |
| `edge` | [DirectedLinkJSON](#directedlinkjson) | The member: a directed link leaving the router. |
| `weight` | integer | Its integer weight (0 included). |

## ModelJSON

| Field | Type | Description |
| --- | --- | --- |
| `routing` | `"shortest_paths"` \| `"distributed_te"` \| `"centralized_te"` \| `"pinned"` | The routing model. |
| `admission` | `"lossless"` \| `"lossy"` | lossless (admit the largest total whose splits fit, and refuse the rest before it enters) or lossy (send the whole offer; what does not fit is lost at the sources or on the links). |
| `allocation` | `"equal"` \| `"weighted"` \| `"optimized"` or null | How a router splits over its members: equal, weighted or optimized. Null when it does not apply to the model. |
| `source_allocation` | `"equal"` \| `"optimized"` \| `"weighted"` or null | How sources share the demand: equal, weighted or optimized. Null when it does not apply to the model. |
| `source_weights` | list of [DeclaredSourceWeightJSON](#declaredsourceweightjson) or null | Weighted sources (CentralizedTE without tunnels): the question's declared weights, each graph node with a nonzero weight in node order (a zero weight receives nothing; all zero gives an empty list); a TE ingress pool's private head is named by its pool. Null when the sources are not weighted. |
| `weight_basis` | `"capacity"` \| `"explicit"` \| `"residual_snapshot"` or null | What weighted splits are proportional to. Null when it does not apply to the model. |
| `edge_weights` | list of [EdgeWeightJSON](#edgeweightjson) or null | Explicit edge weights. Null when the model has none. |
| `tie_break` | `"fewer_hops"` \| `"higher_capacity"` \| `"higher_available_capacity"` \| `"higher_headroom"` or null | How equal-cost choices are ordered (ShortestPaths and T1). Null when the model is another one, or the WCMP controller programs the demand. |
| `multipath` | boolean or null | ShortestPaths: whether every equal-cost walk is used (false: one canonical path). Null when the model is not ShortestPaths, or the WCMP controller programs the demand. |
| `parallel_edges` | boolean or null | ShortestPaths and T1: whether every parallel link is used (false: one per node pair). Null when the model is neither, or the WCMP controller programs the demand. |
| `tunnel_count` | [TunnelCountJSON](#tunnelcountjson) or null | The tunnel count per head. Null when the model has no tunnels. |
| `prefer_headroom` | boolean or null | CentralizedTE: whether T2, after minimizing total tunnel cost, minimizes the plan's headroom penalty, based on occupied fractions of link capacity. Null when the model is not CentralizedTE. |
| `cost_ceiling` | [CostCeilingJSON](#costceilingjson) or null | The tunnels' cost ceiling. Null when there is none. |
| `min_unreserved_bandwidth_units` | integer or null | T1: a setup-search filter (integer units of q): a tunnel's search uses a link only when its unreserved capacity is at least both the tunnel's request and this minimum; nothing is kept free. Null when the model is not T1. |
| `route_names` | list of string or null | The named routes of a pinned model. Null when the model is not pinned by named routes. |
| `controller` | `"next_hop"` \| `"group"` \| `"all_routers"` or null | The WCMP controller scope that programs the demand. Null when no controller programs it. |
| `supplied_support` | boolean | Whether a CentralizedTE model was given its own support DAG. |
| `supplied_program` | boolean | Whether a pinned model was given a native program (its routes are not exported). |

## NamedPathJSON

| Field | Type | Description |
| --- | --- | --- |
| `source` | string | The path's source node. |
| `destination` | string | The path's destination node. |
| `cost` | integer | The path's cost. |
| `hops` | list of list of [DirectedLinkJSON](#directedlinkjson) | The path's hops in order; each hop lists the parallel directed links it may use. |

## NativeOutputsJSON

| Field | Type | Description |
| --- | --- | --- |
| `edge_flows` | boolean | Request each row's per-link flows. |
| `residual` | boolean | Request each row's per-link residual capacity. |
| `edge_reservations` | boolean | Request each row's per-link tunnel holds. |
| `saturated_boundary_edges` | boolean | Request each row's saturated boundary links. |
| `min_cut` | boolean | Request the minimum cut where it is defined. |

## NativePlacementJSON

| Field | Type | Description |
| --- | --- | --- |
| `request_kind` | `"finite"` \| `"unlimited"` | Whether the request is finite or unlimited. |
| `requested_units` | integer or null | The request (integer units of q). Null when the request is unlimited. |
| `offered_units` | integer or null | Lossy: the units sent into the network. Null when admission is lossless. |
| `delivered_units` | integer | The units delivered to the destinations. |
| `unadmitted_units` | integer or null | Lossless: the request minus the delivery; lossy: 0. Null when the request is unlimited. |
| `source_drop_units` | integer | Lossy: units lost at sources without a usable route; 0 when lossless. |
| `edge_drop_units` | integer | Lossy: units dropped on physical links and TE ingress pool attachments, in all; 0 when lossless. |
| `termination` | `"complete"` \| `"no_route"` \| `"exhausted"` \| `"no_active_weight"` | The native call's outcome. Values: complete (the offer is 0, admitted in full when lossless, or forwarded in full when lossy, its losses included); no_route (a positive offer and no source with a route); no_active_weight (the program has routes, but none of positive weight can send anything); exhausted (lossless and less than the offer admitted, or an unlimited offer). |
| `total_cost` | integer or null | The controllers only (CentralizedTE without tunnels, ShortestPaths with optimized allocation): the exact sum over links of cost times carried units. Null when the model is another one (T1, T2, pinned, other ShortestPaths). |
| `call_delivered_units` | integer | The units this call delivered. Absent when details are not requested. |
| `call_undelivered_units` | integer or null | The request minus this call's delivery. Null when the request is unlimited. Absent when details are not requested. |
| `delivery_delta_units` | integer | The delivery after the call minus before it. Absent when details are not requested. |
| `call_edge_drops` | list of [EdgeAmountJSON](#edgeamountjson) | This call's drops on physical links. Absent when details are not requested. |
| `call_source_drop_units` | integer | This call's offered units lost at sources without a usable route. Absent when details are not requested. |
| `admitted_units` | integer | Lossless: the units carried; lossy: the units offered. Absent when details are not requested. |
| `edge_drops` | list of [EdgeAmountJSON](#edgeamountjson) | Drops on physical links, by directed link. Absent when details are not requested. |
| `by_source` | list of [SourceFlowJSON](#sourceflowjson) | One row per source, in source order (zero rows included). Absent when details are not requested. |
| `by_tunnel` | list of [TunnelFlowJSON](#tunnelflowjson) | One row per tunnel of the program, in entry order. Absent when details are not requested. |
| `plan` | [TunnelPlanJSON](#tunnelplanjson) or null | T1 and T2: the tunnel plan after the call. Null when the model is not T1 or T2. Absent when details are not requested, and in a tunnel-count row's result (the row records the plan). |
| `edge_flows` | list of [EdgeAmountJSON](#edgeamountjson) | The units each directed physical link carries. Absent when it was not requested. |
| `residual` | list of [EdgeAmountJSON](#edgeamountjson) | Each directed physical link's residual capacity (integer units of q): after this row, or, in simultaneous placement, the one final residual every row shares. Absent when it was not requested. |
| `edge_reservations` | list of [EdgeAmountJSON](#edgeamountjson) | Each directed physical link's tunnel holds (integer units of q). Absent when it was not requested. |
| `saturated_boundary_edges` | list of [DirectedLinkJSON](#directedlinkjson) | The saturated links at the sources' reachable boundary. Absent when it was not requested. |
| `min_cut` | list of [DirectedLinkJSON](#directedlinkjson) or null | The minimum cut closest to the sources, where one is defined (unrestricted optimized CentralizedTE at its maximum). Null when no cut is defined. Absent when it was not requested. |
| `synthetic_ingress` | [SyntheticProjectionJSON](#syntheticprojectionjson) | Amounts on the private pool attachments (the synthetic ingress edges). Absent when the row has no TE ingress pool, or no native output is requested and details record no attachment drops. |

## NetworkStatsParametersJSON

| Field | Type | Description |
| --- | --- | --- |
| `include_disabled` | boolean | Whether disabled nodes and links are counted. |
| `excluded_nodes` | list of string | Nodes left out of the statistics. |
| `excluded_links` | list of string | Links left out of the statistics. |

## NetworkStatsQuestionJSON

| Field | Type | Description |
| --- | --- | --- |
| `kind` | `"network_stats"` | The record kind, a fixed tag. |
| `parameters` | [NetworkStatsParametersJSON](#networkstatsparametersjson) | The step's parameters. |

## NetworkStatsResultJSON

| Field | Type | Description |
| --- | --- | --- |
| `kind` | `"network_stats"` | The record kind, a fixed tag. |
| `node_count` | integer | Nodes counted. |
| `link_count` | integer | Links counted. |
| `total_capacity` | number | The sum of link capacities. |
| `mean_capacity` | number | The mean link capacity. |
| `median_capacity` | number | The median link capacity. |
| `min_capacity` | number | The smallest link capacity. |
| `max_capacity` | number | The largest link capacity. |
| `mean_cost` | number | The mean link cost. |
| `median_cost` | number | The median link cost. |
| `min_cost` | integer | The smallest link cost. |
| `max_cost` | integer | The largest link cost. |
| `mean_degree` | number | The mean node degree. |
| `median_degree` | number | The median node degree. |
| `min_degree` | number | The smallest node degree. |
| `max_degree` | number | The largest node degree. |

## OutputSelectionJSON

| Field | Type | Description |
| --- | --- | --- |
| `native` | [NativeOutputsJSON](#nativeoutputsjson) | The native output flags. |
| `cost_distribution` | boolean | Whether cost reports are exported. |
| `details` | boolean | Whether native per-source, per-tunnel, plan and call fields are exported. |

## PathAnalysisJSON

| Field | Type | Description |
| --- | --- | --- |
| `kind` | `"paths"` | The record kind, a fixed tag. |
| `metadata` | [AnalysisMetadataJSON](#analysismetadatajson) | Run or analysis metadata. |
| `algorithm` | `"spf"` \| `"ksp"` | The path search: spf (shortest paths) or ksp (k shortest paths). |
| `mode` | `"combine"` \| `"pairwise"` | How sources and targets pair: combine or pairwise. |
| `costs_only` | boolean | Only path costs, without the paths. |
| `rows` | list of [PathRowJSON](#pathrowjson) | The analysis rows, one per demand or endpoint pair. |
| `query` | [PathQueryJSON](#pathqueryjson) | The analysis's typed query (a workflow step records it as the step's question instead). Absent when the analysis is a workflow step's result. |

## PathCostBinJSON

| Field | Type | Description |
| --- | --- | --- |
| `cost` | integer | The path cost (analysis graph for a pool). |
| `physical_path_cost` | integer | The path cost without the pool attachment. |
| `delivered_units` | integer | The units delivered over paths of this cost. |

## PathQueryJSON

| Field | Type | Description |
| --- | --- | --- |
| `kind` | `"paths"` | The record kind, a fixed tag. |
| `source` | [SelectorJSON](#selectorjson) | The source selector. |
| `target` | [SelectorJSON](#selectorjson) | The target selector. |
| `mode` | `"combine"` \| `"pairwise"` | How sources and targets pair: combine or pairwise. |
| `algorithm` | `"spf"` \| `"ksp"` | The path search: spf (shortest paths) or ksp (k shortest paths). |
| `costs_only` | boolean | Only path costs, without the paths. |
| `max_paths` | integer or null | The largest number of paths per row. Null when every path is kept. |
| `split_parallel_edges` | boolean or null | SPF: whether each parallel link is its own path. Null when the algorithm is KSP. |
| `k` | integer or null | KSP: the number of shortest paths. Null when the algorithm is SPF. |
| `cost_ceiling` | [CostCeilingJSON](#costceilingjson) or null | KSP: the cost ceiling. Null when there is none or the algorithm is SPF. |
| `tie_break` | `"fewer_hops"` \| `"higher_capacity"` \| `"higher_available_capacity"` \| `"higher_headroom"` | How equal-cost choices are ordered. |
| `multipath` | boolean or null | SPF: whether every equal-cost walk is used. Null when the algorithm is KSP. |
| `parallel_edges` | boolean | Whether every parallel link is used (false: one per node pair). |
| `excluded_nodes` | list of string or [PoolNodeJSON](#poolnodejson) | Nodes excluded from the question: physical nodes by name, a TE ingress pool's private head by its pool. |
| `excluded_edges` | list of [DirectedLinkJSON](#directedlinkjson) or [SyntheticIngressJSON](#syntheticingressjson) | Directed links excluded from the question. |
| `residual_units` | list of integer or null | The supplied residual capacities the search used (SPF or KSP), one per edge of the prepared graph in edge order (pool attachments included; integer units of q). Null when no residual vector is supplied. |
| `min_residual` | integer or null | SPF: when residual_units is supplied, a link is usable only when that residual is at least this many units; without the vector there is no residual filter (KSP's supplied vector uses a minimum of one unit). Null when the algorithm is KSP. |

## PathRowJSON

| Field | Type | Description |
| --- | --- | --- |
| `id` | string | The row's stable identifier within its analysis. |
| `endpoints` | [EndpointsJSON](#endpointsjson) | The physical source and destination node names of the row. |
| `kind` | `"paths"` \| `"self"` | paths, or self for a source equal to its target. |
| `cost` | integer or null | The shortest cost of the row. Null when the destination is unreachable. |
| `paths` | list of [NamedPathJSON](#namedpathjson) | The paths of this row. Absent when the query is costs-only. |

## PlacementAnalysisJSON

| Field | Type | Description |
| --- | --- | --- |
| `kind` | `"placement"` | The record kind, a fixed tag. |
| `metadata` | [AnalysisMetadataJSON](#analysismetadatajson) | Run or analysis metadata. |
| `outputs` | [OutputSelectionJSON](#outputselectionjson) | The output selection that applies to the rows. |
| `alpha` | [ExactAlphaJSON](#exactalphajson) | The exact scaling of the declared demands. |
| `accounting` | list of [ExpansionAccountingJSON](#expansionaccountingjson) | Each declared demand's units: declared, resolved and discarded. |
| `cases` | list of [PlacementCaseJSON](#placementcasejson) | The baseline case first, then each distinct failure pattern. |
| `query` | [PlacementQueryJSON](#placementqueryjson) | The analysis's typed query (a workflow step records it as the step's question instead). Absent when the analysis is a workflow step's result. |
| `controller` | list of [TableReportJSON](#tablereportjson) | The WCMP controller's tables of this demand set. Absent when no WCMP controller programs the set. |

## PlacementCaseJSON

| Field | Type | Description |
| --- | --- | --- |
| `case` | [FailureCaseJSON](#failurecasejson) | The failure case. |
| `states` | [PlacementStatesJSON](#placementstatesjson) | One entry per requested failure state. |

## PlacementQueryJSON

| Field | Type | Description |
| --- | --- | --- |
| `kind` | `"placement"` | The record kind, a fixed tag. |
| `demand_set` | string | The demand set's name. |
| `demands` | list of [DemandQuestionJSON](#demandquestionjson) | The declared demands of the set, as they were asked. |
| `alpha` | [ExactAlphaJSON](#exactalphajson) | The exact scaling of the declared demands. |
| `alpha_source` | [AlphaSourceJSON](#alphasourcejson) | Where alpha comes from: the query, or an MSD step. |
| `failures` | [FailureRequestJSON](#failurerequestjson) or null | The failure request. Null when the question is the baseline only. |
| `states` | list of `"converged"` \| `"stale"` \| `"repair"` | One entry per requested failure state. |
| `interaction` | `"ordered"` \| `"simultaneous"` | ordered (priority order) or simultaneous (one lossy fixed-program forwarding). |

## PlacementRowJSON

| Field | Type | Description |
| --- | --- | --- |
| `kind` | `"placement"` | The record kind, a fixed tag. |
| `id` | string | The row's stable identifier within its analysis. |
| `base_id` | string | The declared demand's identifier, before expansion. |
| `endpoints` | [EndpointsJSON](#endpointsjson) | The physical source and destination node names of the row. |
| `reference_request_units` | integer | The scaled declared request (integer units of q), the denominator of the delivery ratio. |
| `reference_shortfall_units` | integer | The reference request minus the delivery (integer units of q). |
| `result` | [NativePlacementJSON](#nativeplacementjson) | The native placement result. |
| `pool` | [PoolMetadataJSON](#poolmetadatajson) or null | The TE ingress pool the row's sources share. Null when the sources share no pool. |
| `cost_distribution` | [CostReportJSON](#costreportjson) | The requested cost report. Absent when the report was not requested or is not derivable. |
| `unavailable_outputs` | [UnavailableOutputsJSON](#unavailableoutputsjson) | Requested outputs that the model cannot provide, with the reason. Absent when every requested output is provided. |

## PlacementStateJSON

| Field | Type | Description |
| --- | --- | --- |
| `rows` | list of [PlacementRowJSON](#placementrowjson) | The analysis rows, one per demand or endpoint pair. |
| `totals` | [PlacementTotalsJSON](#placementtotalsjson) or null | Exact totals over the state's rows. Null when the state's forwarding calculation cycled or reached its round limit (see failure). |
| `failure` | [ForwardingFailureJSON](#forwardingfailurejson) | The state's bounded lossy forwarding calculation cycled or reached its round limit. This does not prove that no stable answer exists. Absent when the forwarding calculation finished. |
| `dead_caps` | list of [DeadCapJSON](#deadcapjson) | Declared root groups with no live member in this case, with their fixed caps. Absent when the WCMP controller's scope is not group, and in the stale state. |

## PlacementStatesJSON

| Field | Type | Description |
| --- | --- | --- |
| `converged` | [PlacementStateJSON](#placementstatejson) | The demands computed again on the failed network. Absent when the query does not ask this state. |
| `stale` | [PlacementStateJSON](#placementstatejson) | The no-failure programs forwarded unchanged on the failed network. Absent when the query does not ask this state. |
| `repair` | [PlacementStateJSON](#placementstatejson) | The no-failure programs over their surviving routes. Absent when the query does not ask this state. |

## PlacementTotalsJSON

| Field | Type | Description |
| --- | --- | --- |
| `reference_request_units` | integer | The scaled declared requests over the rows (integer units of q). |
| `delivered_units` | integer | Units delivered over the rows. |
| `unadmitted_units` | integer | Lossless units not admitted over the rows. |
| `source_drop_units` | integer | Lossy units lost at sources over the rows. |
| `edge_drop_units` | integer | Lossy units dropped on physical links and TE ingress pool attachments over the rows. |
| `reference_shortfall_units` | integer | The reference request minus the delivery (integer units of q). |
| `delivery_ratio` | [FractionJSON](#fractionjson) | Delivered over the reference request (a fraction; 1 for no request). |
| `feasible` | boolean | Whether every row delivered its whole reference request, without loss. |

## PoolHeadJSON

| Field | Type | Description |
| --- | --- | --- |
| `pool_id` | string | The pool's identifier. |
| `physical_sources` | list of string | The physical sources behind the pool head. |

## PoolMetadataJSON

| Field | Type | Description |
| --- | --- | --- |
| `head` | [PoolHeadJSON](#poolheadjson) | The pool head and its physical sources. |
| `offer_limit_units` | integer | The prepared lossy offer budget of the pool (integer units of q). |
| `synthetic_ingress_cost` | `1` | The cost of each pool attachment (1). |

## PoolNodeJSON

| Field | Type | Description |
| --- | --- | --- |
| `pool_id` | string | The pool's identifier (as PoolHeadJSON names it). |

## PrecisionMissJSON

| Field | Type | Description |
| --- | --- | --- |
| `location` | [ReportLocationJSON](#reportlocationjson) | Where the miss was observed: step, case and probe. |
| `constraints` | list of [InputConstraintJSON](#inputconstraintjson) or [SplitConstraintJSON](#splitconstraintjson) or [UnverifiedConstraintJSON](#unverifiedconstraintjson) | The constraints the chosen q does not meet there. |
| `inexact_inputs` | integer | Inputs not exact at q there. |
| `zeroed_inputs` | integer | Positive inputs that round to zero units there. |
| `examples` | list of [InputQuantizationJSON](#inputquantizationjson) | Example inputs that miss. |

## PreparationScopeJSON

| Field | Type | Description |
| --- | --- | --- |
| `workflow_steps` | list of string | The workflow steps prepared. |
| `workflow_demand_sets` | list of string | The demand sets the workflow names. |
| `library_demand_sets` | list of string | The demand sets the library caller named. |

## ProbeRowsJSON

| Field | Type | Description |
| --- | --- | --- |
| `index` | integer | The probe's history index. |
| `rows` | list of [PlacementRowJSON](#placementrowjson) | The probe's rows. |

## ProgrammedRouterJSON

| Field | Type | Description |
| --- | --- | --- |
| `router` | string | The programmed router. |
| `members` | list of [MemberWeightJSON](#memberweightjson) | Its members with their integer weights. |

## RangeConstraintJSON

| Field | Type | Description |
| --- | --- | --- |
| `kind` | `"capacity_sum"` \| `"cost_sum"` \| `"amount"` | What is bounded: a capacity sum, a cost sum, or one amount. |
| `label` | string | The input or constraint label: where the value is declared. |
| `tested_q` | number | The q tested. |
| `units_value` | integer | The value at that q (integer units of q). |
| `exclusive_limit` | integer | The exclusive native limit (2^62). |
| `met` | boolean | Whether the value is below the limit. |

## RangeRefusalJSON

| Field | Type | Description |
| --- | --- | --- |
| `label` | string | The input or constraint label: where the value is declared. |
| `reason` | `"scaled_nonfinite"` \| `"native_units_range"` | scaled_nonfinite or native_units_range. |
| `message` | string | The refusal text. |
| `binary64_hex` | string or null | The refused binary64 value in hexadecimal. Null when the refused amount is not a binary64 value. |

## ReportLocationJSON

| Field | Type | Description |
| --- | --- | --- |
| `step` | string or null | The step. Null when the report is outside a workflow. |
| `case_id` | string or null | The case. Null when the report is outside failure cases. |
| `probe_index` | integer or null | The MSD probe. Null when the report is outside MSD. |

## RunJSON

| Field | Type | Description |
| --- | --- | --- |
| `metadata` | [RunMetadataJSON](#runmetadatajson) | The run's metadata: versions and the seed. |
| `steps` | list of [StepResultJSON](#stepresultjson) | The workflow steps in declaration order. |
| `units_report` | [UnitsReportJSON](#unitsreportjson) | The units report of the preparation: q, its reasons, rounding and misses. |

## RunMetadataJSON

| Field | Type | Description |
| --- | --- | --- |
| `schema_version` | `"1.0"` | The results schema version. |
| `netgraph_version` | string | The installed ngraph package version. |
| `core_version` | string | The netgraph-core version. |
| `core_extension_sha256` | string | The SHA-256 of the loaded native extension. |
| `python_version` | string | The Python version. |
| `seed` | integer or null | The scenario seed. Null when the scenario sets no seed. |

## SamplingMetadataJSON

| Field | Type | Description |
| --- | --- | --- |
| `random_rule_algorithm` | `"per_entity_bernoulli"` | The random-rule algorithm: one Bernoulli trial per entity. |
| `rng` | `"random.Random"` | The random number generator. |
| `python_version` | string | The Python version that drew. |
| `seed` | integer or null | The base seed. Null when the draws are unseeded. |
| `seed_source` | `"query"` \| `"step"` \| `"scenario"` \| `"policy"` \| `"unseeded"` | Where the base seed comes from. |
| `draw_seed_rule` | `"base_plus_draw_index"` | Draw i uses the base seed plus i. |
| `entity_order` | `"sorted_identifier"` | Entities are drawn in sorted identifier order. |
| `rule_order` | `"declaration"` | Rules are applied in declaration order. |
| `iterations` | integer | The number of draws. |

## SelectorJSON

| Field | Type | Description |
| --- | --- | --- |
| `path` | string or null | The path pattern (a regular expression matched at the start of node names). Null when every node is selected. |
| `group_by` | string or null | A node attribute that groups the selection. Null when there is none. |
| `match` | object or null | Attribute conditions that filter the selection. Null when there are none. |
| `active_only` | boolean or null | Whether disabled nodes are left out. Null when the caller's default applies. |

## SelfPairJSON

| Field | Type | Description |
| --- | --- | --- |
| `kind` | `"self"` | The record kind, a fixed tag. |
| `id` | string | The row's stable identifier within its analysis. |
| `node` | string | The node that is both source and target. |
| `capacity_units` | `0` | Always 0: a node's capacity to itself is not a question. |

## SensitivityAnalysisJSON

| Field | Type | Description |
| --- | --- | --- |
| `kind` | `"sensitivity"` | The record kind, a fixed tag. |
| `metadata` | [AnalysisMetadataJSON](#analysismetadatajson) | Run or analysis metadata. |
| `outputs` | [OutputSelectionJSON](#outputselectionjson) | The output selection that applies to the rows. |
| `endpoints` | [EndpointsJSON](#endpointsjson) | The physical source and destination node names of the row. |
| `question` | `"lossless_bound"` \| `"fixed_offer_delivery"` | The question this step or analysis asked. |
| `offer_source` | `"unlimited"` \| `"explicit"` \| `"design"` | Where the offer comes from: unlimited, explicit or the design demand. |
| `baseline` | [NativePlacementJSON](#nativeplacementjson) | The native result without deletions. |
| `entries` | list of [SensitivityEntryJSON](#sensitivityentryjson) | Each directed link whose deletion changes delivery, with the reduction. |
| `query` | [SensitivityQueryJSON](#sensitivityqueryjson) | The analysis's typed query (a workflow step records it as the step's question instead). Absent when the analysis is a workflow step's result. |

## SensitivityEntryJSON

| Field | Type | Description |
| --- | --- | --- |
| `edge` | [DirectedLinkJSON](#directedlinkjson) | The directed physical link. |
| `delivery_reduction_units` | integer | Baseline delivery minus the delivery without this link (negative: deleting it helps). |

## SensitivityQueryJSON

| Field | Type | Description |
| --- | --- | --- |
| `kind` | `"sensitivity"` | The record kind, a fixed tag. |
| `source` | [SelectorJSON](#selectorjson) | The source selector. |
| `target` | [SelectorJSON](#selectorjson) | The target selector. |
| `model` | [ModelJSON](#modeljson) | The routing model and admission of the question. |
| `offer` | number or null | The physical offer. Null when no offer is set. |
| `design_demand` | number or null | The physical design volume of tunnels. Null when no design volume is set. |
| `excluded_nodes` | list of string or [PoolNodeJSON](#poolnodejson) | Nodes excluded from the question: physical nodes by name, a TE ingress pool's private head by its pool. |
| `excluded_edges` | list of [DirectedLinkJSON](#directedlinkjson) or [SyntheticIngressJSON](#syntheticingressjson) | Directed links excluded from the question. |

## SourceFlowJSON

| Field | Type | Description |
| --- | --- | --- |
| `source` | [SourceJSON](#sourcejson) | The source: a node name, or the pool head of a TE ingress pool. |
| `offered_units` | integer or null | Lossy: the units this source sent. Null when admission is lossless. |
| `admitted_units` | integer | Lossless: the units it delivers; lossy: offered. |
| `delivered_units` | integer | The units this source delivers. |
| `source_drop_units` | integer | Lossy: units lost at sources without a usable route; 0 when lossless. |
| `total_edge_drop_units` | integer | Lossy: this source's units dropped on physical links and TE ingress pool attachments; 0 when lossless. |

## SourceJSON

One of: string or [PoolHeadJSON](#poolheadjson).

## SourceWeightJSON

| Field | Type | Description |
| --- | --- | --- |
| `source` | string | The source node. |
| `nominal_physical` | [FractionJSON](#fractionjson) | Its share of declared physical volumes toward the destination (a fraction, before alpha). |
| `weight` | integer | Its integer source weight. |

## SplitConstraintJSON

| Field | Type | Description |
| --- | --- | --- |
| `kind` | `"expansion"` \| `"source"` \| `"router"` \| `"tunnel"` | Where the split is: expansion, sources, a router or tunnels. |
| `label` | string | The input or constraint label: where the value is declared. |
| `incoming_physical` | [FractionJSON](#fractionjson) | The physical amount split (a fraction). |
| `basis` | `"declared"` \| `"observed"` | declared (from the demands) or observed (from an analysis). |
| `members` | integer | The members the amount is split over. |
| `q_upper_bound` | [FractionJSON](#fractionjson) | The q bound this split records: the precision times the incoming amount divided by (members - 1). It bounds q, not the split's own error. |
| `met` | boolean | Whether the chosen q meets it. |

## StandaloneAnalysisJSON

| Field | Type | Description |
| --- | --- | --- |
| `metadata` | [RunMetadataJSON](#runmetadatajson) | The export's metadata: versions. |
| `analysis` | [AnalysisJSON](#analysisjson) (with `query`) | The exported analysis. |
| `units_report` | [UnitsReportJSON](#unitsreportjson) | The units report of the preparation: q, its reasons, rounding and misses. |

## StepQuestionJSON

One of: [CapacityQueryJSON](#capacityqueryjson) or [PlacementQueryJSON](#placementqueryjson) or [SensitivityQueryJSON](#sensitivityqueryjson) or [PathQueryJSON](#pathqueryjson) or [MSDQueryJSON](#msdqueryjson) or [TunnelCountQueryJSON](#tunnelcountqueryjson) or [DomainQuestionJSON](#domainquestionjson) or [CustomQuestionJSON](#customquestionjson).

## StepResultJSON

| Field | Type | Description |
| --- | --- | --- |
| `name` | string | The workflow step's name. |
| `step_type` | string | The step's class name. |
| `execution_order` | integer | The step's position in the run (0 first). |
| `scenario_seed` | integer or null | The scenario seed. Null when the scenario sets no seed. |
| `step_seed` | integer or null | The step's effective seed. Null when the step has no effective seed. |
| `seed_source` | `"explicit-step"` \| `"scenario-derived"` \| `"none"` | Where the step's seed comes from. |
| `result` | [AnalysisJSON](#analysisjson) or [DomainResultJSON](#domainresultjson) or [JSONValue](#jsonvalue) | The step's exported result. Null when a custom step returns no result, or its registered exporter writes null. |
| `question` | [StepQuestionJSON](#stepquestionjson) | The question the step asked. |

## SyntheticAmountJSON

| Field | Type | Description |
| --- | --- | --- |
| `edge` | [SyntheticIngressJSON](#syntheticingressjson) | The pool attachment: its pool and source. |
| `units` | integer | The amount (integer units of q). |

## SyntheticIngressJSON

| Field | Type | Description |
| --- | --- | --- |
| `pool_id` | string | The pool's identifier. |
| `source` | string | The physical source this attachment feeds. |

## SyntheticProjectionJSON

| Field | Type | Description |
| --- | --- | --- |
| `call_edge_drops` | list of [SyntheticAmountJSON](#syntheticamountjson) | This call's drops on pool attachments. Absent when details are not requested. |
| `edge_drops` | list of [SyntheticAmountJSON](#syntheticamountjson) | Drops on pool attachments. Absent when details are not requested. |
| `edge_flows` | list of [SyntheticAmountJSON](#syntheticamountjson) | The units each pool attachment carries. Absent when it was not requested. |
| `residual` | list of [SyntheticAmountJSON](#syntheticamountjson) | Each pool attachment's residual capacity (integer units of q): after this row, or, in simultaneous placement, the one final residual every row shares. Absent when it was not requested. |
| `edge_reservations` | list of [SyntheticAmountJSON](#syntheticamountjson) | Each pool attachment's holds (integer units of q). Absent when it was not requested. |
| `saturated_boundary_edges` | list of [SyntheticIngressJSON](#syntheticingressjson) | The saturated pool attachments at the boundary. Absent when it was not requested. |
| `min_cut` | list of [SyntheticIngressJSON](#syntheticingressjson) or null | The pool attachments in the minimum cut. Null when no cut is defined. Absent when it was not requested. |

## TableReportJSON

| Field | Type | Description |
| --- | --- | --- |
| `destination` | string | The destination of the table. |
| `programmed` | list of [ProgrammedRouterJSON](#programmedrouterjson) | The routers the controller programs, with their member weights. |
| `source_weights` | list of [SourceWeightJSON](#sourceweightjson) or null | all_routers: each source's share of declared physical volumes and its weight. Null when the scope is not all_routers. |

## TunnelCountAnalysisJSON

| Field | Type | Description |
| --- | --- | --- |
| `kind` | `"tunnel_counts"` | The record kind, a fixed tag. |
| `metadata` | [AnalysisMetadataJSON](#analysismetadatajson) | Run or analysis metadata. |
| `outputs` | [OutputSelectionJSON](#outputselectionjson) | The output selection that applies to the rows. |
| `rows` | list of [TunnelCountRowJSON](#tunnelcountrowjson) | One row per demand and tunnel count. |
| `query` | [TunnelCountQueryJSON](#tunnelcountqueryjson) | The analysis's typed query (a workflow step records it as the step's question instead). Absent when the analysis is a workflow step's result. |

## TunnelCountJSON

| Field | Type | Description |
| --- | --- | --- |
| `per_head` | integer | Tunnels per head. |
| `up_to` | boolean | Whether the count is a limit: every head gets one common count up to it, the smallest whose program carries the live heads' design shares (if none does, the count with the largest live-share score, then the smallest). |

## TunnelCountQueryJSON

| Field | Type | Description |
| --- | --- | --- |
| `kind` | `"tunnel_counts"` | The record kind, a fixed tag. |
| `demand_set` | string | The demand set's name. |
| `demands` | list of [DemandQuestionJSON](#demandquestionjson) | The declared demands of the set, as they were asked. |
| `counts` | list of integer | The tunnel counts asked, one row each per demand. |
| `up_to` | integer or null | The up-to limit asked. Null when there is none. |
| `design_demand` | number | The physical design volume of every demand. |
| `offer` | number | The physical offer of every demand. |
| `excluded_nodes` | list of string or [PoolNodeJSON](#poolnodejson) | Nodes excluded from the question: physical nodes by name, a TE ingress pool's private head by its pool. |
| `excluded_edges` | list of [DirectedLinkJSON](#directedlinkjson) or [SyntheticIngressJSON](#syntheticingressjson) | Directed links excluded from the question. |

## TunnelCountRowJSON

| Field | Type | Description |
| --- | --- | --- |
| `id` | string | The row's stable identifier within its analysis. |
| `base_id` | string | The declared demand's identifier, before expansion. |
| `endpoints` | [EndpointsJSON](#endpointsjson) | The physical source and destination node names of the row. |
| `count` | integer | The tunnels per head of this row (an up-to row: its limit). |
| `up_to` | boolean | Whether this row is the up-to row. |
| `pool` | [PoolMetadataJSON](#poolmetadatajson) or null | The TE ingress pool the row's sources share. Null when the sources share no pool. |
| `lossless_at_design_units` | integer | The lossless delivery at the design volume: min(design, the plan's lossless maximum). |
| `physical_tunnel_cost` | integer | For a TE ingress pool: the total tunnel cost without the pool attachments; else the total tunnel cost. |
| `plan` | [TunnelPlanJSON](#tunnelplanjson) | The tunnel plan after the call. |
| `result` | [NativePlacementJSON](#nativeplacementjson) (without `plan`) | The native placement result. |

## TunnelFlowJSON

| Field | Type | Description |
| --- | --- | --- |
| `entry_id` | integer | The tunnel's entry identifier in the program. |
| `head` | [SourceJSON](#sourcejson) | The tunnel head: a node name, or the pool head of a TE ingress pool. |
| `status` | `"up"` \| `"insufficient_bandwidth"` \| `"cost_ceiling_exceeded"` \| `"failed"` \| `"blackholed"` | The tunnel's status in this forwarding. Values: up (set up and available for forwarding; it may carry zero units); insufficient_bandwidth (down: no path had enough unreserved bandwidth); cost_ceiling_exceeded (down: the cheapest path with enough bandwidth costs more than the cost ceiling); failed (repair state: a failure touches the tunnel, so its route is removed); blackholed (stale state: the tunnel stays up but its path reaches a failed node or link, where its traffic is dropped). |
| `assigned_units` | integer | The units assigned to the tunnel (lossy: sent to it; lossless: carried). |
| `delivered_units` | integer | The units this tunnel delivers. |
| `total_edge_drop_units` | integer | Lossy: this tunnel's units dropped on physical links and TE ingress pool attachments; 0 when lossless. |

## TunnelPlanJSON

| Field | Type | Description |
| --- | --- | --- |
| `tunnels_per_head` | integer | Tunnels per head (an up-to count: the chosen count). |
| `design_kind` | `"finite"` \| `"unlimited"` | Whether the design volume is finite or unlimited. |
| `design_demand_units` | integer or null | The design volume D (integer units of q). Null when the design is unlimited. |
| `design_by_head` | list of [HeadDesignJSON](#headdesignjson) | Each head's share of the design volume. |
| `total_reserved_bandwidth_units` | integer | The holds of the up tunnels (integer units of q). |
| `heads_with_capacity` | list of [SourceJSON](#sourcejson) or null | T2: the live heads, those that reach a destination over links with at least one free unit (this policy's own traffic released). Null when the plan is T1's. |
| `insufficient_resolution` | boolean or null | T2: live heads exist but no whole unit per tunnel fits. Null when the plan is T1's. |
| `max_fractional_bandwidth_per_tunnel` | [FractionJSON](#fractionjson) or null | T2: the exact fluid optimum per tunnel (a fraction). Null when the plan is T1's. |
| `max_bandwidth_per_tunnel_units` | integer or null | T2: the largest common whole-unit tunnel size U. Null when the plan is T1's. |
| `planned_bandwidth_per_tunnel_units` | integer or null | T2: every tunnel's planned bandwidth u. Null when the plan is T1's. |
| `total_planned_bandwidth_units` | integer or null | T2: the planned bandwidth over all tunnels. Null when the plan is T1's. |
| `total_tunnel_cost` | integer or null | T2: the sum of link cost times tunnel count over the links (exact). Null when the plan is T1's. |
| `headroom_penalty` | integer or null | T2 with prefer_headroom: the headroom penalty of the plan. Null when the plan is T1's or prefer_headroom is off. |
| `max_lossless_offer_units` | integer or null | T2: the program's lossless maximum offer F. Null when the plan is T1's. |

## UnavailableOutputsJSON

| Field | Type | Description |
| --- | --- | --- |
| `cost_distribution` | [CostUnavailableReasonJSON](#costunavailablereasonjson) | Why the cost report is not derivable for this row. Absent when it is derivable or was not requested. |

## UnitConstraintJSON

One of: [InputConstraintJSON](#inputconstraintjson) or [SplitConstraintJSON](#splitconstraintjson) or [RangeConstraintJSON](#rangeconstraintjson) or [UnverifiedConstraintJSON](#unverifiedconstraintjson).

## UnitsReportJSON

| Field | Type | Description |
| --- | --- | --- |
| `q` | number | The bandwidth unit: one unit is q in physical terms. |
| `exponent` | integer | q as a power of two: q = 2^exponent. |
| `mode` | `"auto"` \| `"manual"` | auto (chosen by the recipe) or manual (declared). |
| `precision` | number | The relative precision target. |
| `target_met` | boolean | Whether every declared input and split meets its precision bound at q. The bound is checked, not the rounding: false is possible with no input rounded. |
| `input_convention` | `"promoted_binary64_half_up"` | Physical inputs round half-up from their binary64 value. |
| `display_convention` | `"units_authoritative_binary64_display"` | Units are authoritative; physical values are binary64 displays. |
| `scope` | [PreparationScopeJSON](#preparationscopejson) | What the preparation covered. |
| `binding_constraints` | list of [UnitConstraintJSON](#unitconstraintjson) | The constraints that limited q. |
| `input_count` | integer | Physical inputs converted to units. |
| `inexact_inputs` | integer | Inputs not exact at q. |
| `zeroed_inputs` | integer | Positive inputs that round to zero units. |
| `inexact_examples` | list of [InputQuantizationJSON](#inputquantizationjson) | Example inexact inputs. |
| `zeroed_examples` | list of [InputQuantizationJSON](#inputquantizationjson) | Example zeroed inputs. |
| `max_absolute_input_error` | [FractionJSON](#fractionjson) | The largest absolute input error (physical, a fraction). |
| `max_relative_input_error` | [FractionJSON](#fractionjson) | The largest absolute relative input error (a fraction). |
| `augmented_capacity_sum_units` | integer | The graph's capacity sum with pool attachments (integer units of q). |
| `augmented_cost_sum` | integer | The graph's cost sum with pool attachments. |
| `nominal_split_count` | integer | Splits of the demands at alpha 1 without failures. |
| `nominal_splits` | list of [SplitConstraintJSON](#splitconstraintjson) | Those splits with their bounds on q. |
| `misses` | list of [PrecisionMissJSON](#precisionmissjson) | Precision misses observed in analyses. |
| `weight_approximations` | list of [WeightApproximationJSON](#weightapproximationjson) | Controller weights apportioned because they reached 2^62. |

## UnverifiedConstraintJSON

| Field | Type | Description |
| --- | --- | --- |
| `kind` | `"unverified"` | The record kind, a fixed tag. |
| `label` | string | The input or constraint label: where the value is declared. |
| `reason` | `"opaque_program"` | The split is inside a supplied native program NetGraph cannot inspect. |

## UpperCertificateJSON

| Field | Type | Description |
| --- | --- | --- |
| `proof` | `"fixed_program"` \| `"single_controller"` | What proves the bracket. |
| `lower` | [ExactAlphaJSON](#exactalphajson) | The feasible lower alpha. |
| `upper` | [ExactAlphaJSON](#exactalphajson) | The infeasible upper alpha. |
| `lower_probe_index` | integer | The history index of the lower probe. |
| `upper_probe_index` | integer | The history index of the upper probe. |

## WeightApproximationJSON

| Field | Type | Description |
| --- | --- | --- |
| `kind` | `"weight_approximation"` | The record kind, a fixed tag. |
| `label` | string | The router (controller.<set>.<t>.router.<r>) or all_routers source (controller.<set>.<t>.source.<s>) whose weights were apportioned. |
| `max_relative_error` | [FractionJSON](#fractionjson) | The largest relative error of the apportioned weights (a fraction). |
