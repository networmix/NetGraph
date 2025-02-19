from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from ngraph.lib.graph import StrictMultiDiGraph, NodeID


def graph_to_node_link(graph: StrictMultiDiGraph) -> Dict:
    """
    Return a node-link representation of a StrictMultiDiGraph, suitable
    for direct JSON serialization (e.g., for D3.js or Nx node-link formats).

    The returned dict has this structure:
    {
      "graph": { ... top-level graph attributes ... },
      "nodes": [
        {"id": node_id, "attr": {... node attributes ...}},
        ...
      ],
      "links": [
        {
          "source": <indexed_node>,
          "target": <indexed_node>,
          "key": <edge_id>,
          "attr": {... edge attributes ...}
        },
        ...
      ]
    }

    :param graph: The StrictMultiDiGraph to convert.
    :return: A dict with 'graph', 'nodes', and 'links' keys.
    """
    node_dict = graph.get_nodes()
    node_list = list(node_dict.keys())  # stable ordering
    node_map = {node_id: i for i, node_id in enumerate(node_list)}

    return {
        "graph": dict(graph.graph),
        "nodes": [
            {
                "id": node_id,
                "attr": dict(node_dict[node_id]),
            }
            for node_id in node_list
        ],
        "links": [
            {
                "source": node_map[src],
                "target": node_map[dst],
                "key": edge_id,
                "attr": dict(edge_attrs),
            }
            for edge_id, (src, dst, _, edge_attrs) in graph.get_edges().items()
        ],
    }


def node_link_to_graph(data: Dict) -> StrictMultiDiGraph:
    """
    Given a node-link representation (e.g. from `graph_to_node_link`),
    reconstruct and return a StrictMultiDiGraph.

    Expected format in `data`:
    {
      "graph": {... Nx graph attributes ...},
      "nodes": [
        {
          "id": <node_id>,
          "attr": {... node attributes ...}
        },
        ...
      ],
      "links": [
        {
          "source": <indexed_node>,
          "target": <indexed_node>,
          "key": <edge_id>,
          "attr": {... edge attributes ...}
        },
        ...
      ]
    }

    :param data: Dict representing the node-link structure.
    :return: A newly constructed StrictMultiDiGraph with the same nodes/edges.
    """
    # Create the graph with top-level 'graph' attributes
    graph_attrs = data.get("graph", {})
    graph = StrictMultiDiGraph(**graph_attrs)

    node_map: Dict[int, NodeID] = {}
    # Re-add nodes, capturing integer indices -> node IDs
    for idx, node_obj in enumerate(data.get("nodes", [])):
        node_id = node_obj["id"]
        graph.add_node(node_id, **node_obj["attr"])
        node_map[idx] = node_id

    # Re-add edges
    for edge_obj in data.get("links", []):
        src_id = node_map[edge_obj["source"]]
        dst_id = node_map[edge_obj["target"]]
        edge_key = edge_obj.get("key", None)
        edge_attr = edge_obj.get("attr", {})
        graph.add_edge(src_id, dst_id, key=edge_key, **edge_attr)

    return graph


def edgelist_to_graph(
    lines: Iterable[str],
    columns: List[str],
    separator: str = " ",
    graph: Optional[StrictMultiDiGraph] = None,
    source: str = "src",
    target: str = "dst",
    key: str = "key",
) -> StrictMultiDiGraph:
    """
    Build or update a StrictMultiDiGraph using lines from an edge list.

    Each line is split by `separator` into exactly `len(columns)` tokens,
    then mapped into { columns[i]: token[i] }. The fields named by `source` and
    `target` are the node IDs; if a `key` column is present, that token is used
    as the edge ID; all other columns become edge attributes.

    :param lines: Iterable of strings, each describing one edge.
    :param columns: Column names, e.g. ["src", "dst", "cost"].
    :param separator: Token separator for each line (default space).
    :param graph: If provided, the existing StrictMultiDiGraph to modify; else create a new one.
    :param source: Name of the column holding the source node ID.
    :param target: Name of the column holding the target node ID.
    :param key: Name of the column holding a custom edge ID (if any).
    :return: The updated (or newly created) StrictMultiDiGraph.
    """
    if graph is None:
        graph = StrictMultiDiGraph()

    for line in lines:
        # Only strip newlines, not all whitespace
        line = line.rstrip("\r\n")
        tokens = line.split(separator)
        if len(tokens) != len(columns):
            raise RuntimeError(
                f"Line '{line}' does not match expected columns {columns} (token count mismatch)."
            )

        line_dict = dict(zip(columns, tokens))
        src_id = line_dict[source]
        dst_id = line_dict[target]
        edge_key = line_dict.get(key, None)

        # Everything else is an attribute
        attr_dict = {
            k: v for k, v in line_dict.items() if k not in (source, target, key)
        }

        # Because StrictMultiDiGraph does not auto-create nodes
        if src_id not in graph:
            graph.add_node(src_id)
        if dst_id not in graph:
            graph.add_node(dst_id)

        graph.add_edge(src_id, dst_id, key=edge_key, **attr_dict)

    return graph


def graph_to_edgelist(
    graph: StrictMultiDiGraph,
    columns: Optional[List[str]] = None,
    separator: str = " ",
    source_col: str = "src",
    target_col: str = "dst",
    key_col: str = "key",
) -> List[str]:
    """
    Convert a StrictMultiDiGraph into an edge-list text representation.

    Each returned line has tokens for columns, joined by `separator`.
    By default, the columns are:
      [source_col, target_col, key_col] + sorted(edge_attribute_names)

    If you pass an explicit `columns` list, that exact order is used
    (and any missing columns are left blank in that line).

    :param graph: The StrictMultiDiGraph to export.
    :param columns: Optional list of column names. If None, we auto-generate them.
    :param separator: The string used to join column tokens (default space).
    :param source_col: Name for the source node column (default "src").
    :param target_col: Name for the target node column (default "dst").
    :param key_col: Name for the edge key column (default "key").
    :return: A list of lines, each describing one edge in column-based form.
    """
    edge_dicts: List[Dict[str, str]] = []
    all_attr_keys = set()

    for edge_id, (src, dst, _, edge_attrs) in graph.get_edges().items():
        row = {
            source_col: str(src),
            target_col: str(dst),
            key_col: str(edge_id) if edge_id else "",
        }
        for attr_key, attr_val in edge_attrs.items():
            row[attr_key] = str(attr_val)
            all_attr_keys.add(attr_key)
        edge_dicts.append(row)

    # Auto-generate columns if not provided
    if columns is None:
        sorted_attr_keys = sorted(all_attr_keys)
        columns = [source_col, target_col, key_col] + sorted_attr_keys

    lines: List[str] = []
    for row_dict in edge_dicts:
        # For each column, output either the stored string or "" if absent
        tokens = [row_dict.get(col, "") for col in columns]
        lines.append(separator.join(tokens))

    return lines
