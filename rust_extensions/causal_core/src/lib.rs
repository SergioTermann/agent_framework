use pyo3::prelude::*;
use std::collections::{HashMap, HashSet, VecDeque};

type EdgeRecord = (usize, String, String);

fn build_adjacency(edges: &[EdgeRecord]) -> HashMap<String, Vec<(usize, String)>> {
    let mut adjacency: HashMap<String, Vec<(usize, String)>> = HashMap::new();
    for (edge_id, source, target) in edges {
        adjacency
            .entry(source.clone())
            .or_default()
            .push((*edge_id, target.clone()));
    }
    adjacency
}

fn dfs_find_paths(
    adjacency: &HashMap<String, Vec<(usize, String)>>,
    current: &str,
    end: &str,
    max_depth: usize,
    depth: usize,
    visited: &mut HashSet<String>,
    current_path: &mut Vec<usize>,
    results: &mut Vec<Vec<usize>>,
) {
    if depth > max_depth {
        return;
    }

    if current == end {
        results.push(current_path.clone());
        return;
    }

    if !visited.insert(current.to_string()) {
        return;
    }

    if let Some(children) = adjacency.get(current) {
        for (edge_id, target) in children {
            current_path.push(*edge_id);
            dfs_find_paths(
                adjacency,
                target,
                end,
                max_depth,
                depth + 1,
                visited,
                current_path,
                results,
            );
            current_path.pop();
        }
    }

    visited.remove(current);
}

fn dfs_detect_cycles(
    adjacency: &HashMap<String, Vec<(usize, String)>>,
    node_id: &str,
    visited: &mut HashSet<String>,
    rec_stack: &mut HashSet<String>,
    path: &mut Vec<String>,
    cycles: &mut Vec<Vec<String>>,
) {
    visited.insert(node_id.to_string());
    rec_stack.insert(node_id.to_string());
    path.push(node_id.to_string());

    if let Some(children) = adjacency.get(node_id) {
        for (_, child) in children {
            if !visited.contains(child) {
                dfs_detect_cycles(adjacency, child, visited, rec_stack, path, cycles);
            } else if rec_stack.contains(child) {
                if let Some(start) = path.iter().position(|n| n == child) {
                    let mut cycle = path[start..].to_vec();
                    cycle.push(child.clone());
                    cycles.push(cycle);
                }
            }
        }
    }

    path.pop();
    rec_stack.remove(node_id);
}

#[pyfunction]
fn find_paths(
    edges: Vec<EdgeRecord>,
    start_id: String,
    end_id: String,
    max_depth: usize,
) -> PyResult<Vec<Vec<usize>>> {
    let adjacency = build_adjacency(&edges);
    let mut visited = HashSet::new();
    let mut current_path = Vec::new();
    let mut results = Vec::new();

    dfs_find_paths(
        &adjacency,
        &start_id,
        &end_id,
        max_depth,
        0,
        &mut visited,
        &mut current_path,
        &mut results,
    );

    Ok(results)
}

#[pyfunction]
fn shortest_path(edges: Vec<EdgeRecord>, start_id: String, end_id: String) -> PyResult<Vec<usize>> {
    if start_id == end_id {
        return Ok(Vec::new());
    }

    let adjacency = build_adjacency(&edges);
    let mut visited: HashSet<String> = HashSet::new();
    let mut queue: VecDeque<(String, Vec<usize>)> = VecDeque::new();

    visited.insert(start_id.clone());
    queue.push_back((start_id, Vec::new()));

    while let Some((current, edge_path)) = queue.pop_front() {
        if current == end_id {
            return Ok(edge_path);
        }

        if let Some(children) = adjacency.get(&current) {
            for (edge_id, target) in children {
                if visited.insert(target.clone()) {
                    let mut next_path = edge_path.clone();
                    next_path.push(*edge_id);
                    queue.push_back((target.clone(), next_path));
                }
            }
        }
    }

    Ok(Vec::new())
}

#[pyfunction]
fn detect_cycles(edges: Vec<EdgeRecord>) -> PyResult<Vec<Vec<String>>> {
    let adjacency = build_adjacency(&edges);
    let mut visited: HashSet<String> = HashSet::new();
    let mut rec_stack: HashSet<String> = HashSet::new();
    let mut path: Vec<String> = Vec::new();
    let mut cycles: Vec<Vec<String>> = Vec::new();

    let mut nodes: HashSet<String> = HashSet::new();
    for (_, source, target) in &edges {
        nodes.insert(source.clone());
        nodes.insert(target.clone());
    }

    for node_id in nodes {
        if !visited.contains(&node_id) {
            dfs_detect_cycles(
                &adjacency,
                &node_id,
                &mut visited,
                &mut rec_stack,
                &mut path,
                &mut cycles,
            );
        }
    }

    Ok(cycles)
}

#[pymodule]
fn causal_core(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(find_paths, m)?)?;
    m.add_function(wrap_pyfunction!(shortest_path, m)?)?;
    m.add_function(wrap_pyfunction!(detect_cycles, m)?)?;
    Ok(())
}
