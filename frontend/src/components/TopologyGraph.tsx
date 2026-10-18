import { useI18n } from '../i18n';
import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent } from 'react';
import { ReactFlow, Controls, MiniMap, Handle, MarkerType, NodeResizer, Position, applyNodeChanges, type Connection as GraphConnection, type Node, type NodeChange, type NodeProps, type ReactFlowInstance } from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { kindOf, parentId, type Config, type EntityKind, type Geometry, type Selection, type View } from '../topology';
import { Icon } from './Common';
import { snapTopologyPositions, TOPOLOGY_SNAP_GRID } from '../topology-grid';

type NodeData = { name: string; kind: EntityKind; description: string; editable: boolean; collapsed: boolean; minWidth: number; minHeight: number; addChildDisabled: boolean; addChildNeedsParser: boolean; onAddChild?: () => void; onSelect: (additive?: boolean) => void; onCollapse: () => void; onResize: (geometry: { x: number; y: number; width: number; height: number }) => void };
type DiagramNode = Node<NodeData>;

function TopologyNode({ data, selected }: NodeProps<DiagramNode>) {
  const { t } = useI18n();
  const process = data.kind === 'process';
  const addLabel = data.kind === 'server' ? t('Add process to {name}', { name: data.name }) : t('Add server to {name}', { name: data.name });
  return <div className={`diagram-node ${data.kind}-card ${selected ? 'selected' : ''} ${data.collapsed ? 'collapsed' : ''}`}>
    <NodeResizer isVisible={selected && data.editable && !data.collapsed} minWidth={data.minWidth} minHeight={data.minHeight} onResizeEnd={(_event, parameters) => data.onResize(parameters)} />
    {process ? <>
      <Handle type="target" position={Position.Left} isConnectable={data.editable} />
      <button title={t("Select this process and read its documentation.")} className={`process-card ${selected ? 'selected' : ''}`} aria-label={t("Select process {name}", { name: data.name })} aria-pressed={selected} onClick={event => { event.stopPropagation(); data.onSelect(event.ctrlKey || event.metaKey || event.shiftKey); }}><Icon kind="process" /><span><strong>{data.name}</strong><small>{data.description || t("Configured process")}</small></span><span className="access-state">{t("Not checked")}</span></button>
      <Handle type="source" position={Position.Right} isConnectable={data.editable} />
    </> : <header className="node-header"><button title={t("Select this element and read its documentation.")} className="node-label nodrag" onClick={event => { event.stopPropagation(); data.onSelect(event.ctrlKey || event.metaKey || event.shiftKey); }} aria-label={data.kind === 'server' ? t('Select server {name}', { name: data.name }) : t('Select subsystem {name}', { name: data.name })}><Icon kind={data.kind === 'server' ? 'server' : 'system'} /><strong>{data.name}</strong></button><span className="node-frame-actions nodrag nopan" onPointerDown={event => event.stopPropagation()} onMouseDown={event => event.stopPropagation()} onKeyDown={event => event.stopPropagation()}>
      {data.onAddChild && <button type="button" className="node-add-button" aria-label={addLabel} title={data.addChildNeedsParser ? t('Add a parser profile before adding a process.') : addLabel} disabled={data.addChildDisabled} onClick={event => { event.stopPropagation(); data.onAddChild?.(); }}>+</button>}
      <button type="button" title={data.collapsed ? t("Show the elements inside this group.") : t("Hide the elements inside this group.")} className="collapse-button" aria-label={data.collapsed ? t('Expand {name}', { name: data.name }) : t('Collapse {name}', { name: data.name })} aria-expanded={!data.collapsed} onClick={event => { event.stopPropagation(); data.onCollapse(); }}><Icon kind={data.collapsed ? 'expand' : 'collapse'} /></button>
    </span></header>}
  </div>;
}

const nodeTypes = { topology: TopologyNode };

export default function TopologyGraph({ config, view, editable, selection, selectedIds, highlighted, reveal, saving, onSelect, onMultiSelect, onGeometry, onCollapse, onConnect, onAddChild }: {
  config: Config; view: View; editable: boolean; selection: Selection | null; selectedIds: string[]; highlighted: Set<string>; reveal: number; saving: boolean;
  onSelect: (selection: Selection, additive?: boolean) => void; onMultiSelect: (ids: string[]) => void;
  onGeometry: (id: string, geometry: Partial<Geometry>, moved?: { id: string; position: { x: number; y: number } }[]) => void; onCollapse: (id: string) => void; onConnect: (source: string, target: string) => void;
  onAddChild: (parent: { kind: 'subsystem' | 'server'; id: string }) => void;
}) {
  const { t } = useI18n();
  const instance = useRef<ReactFlowInstance<DiagramNode> | null>(null);
  const [nodes, setNodes] = useState<DiagramNode[]>([]);
  const [theme, setTheme] = useState<'light' | 'dark'>(() => document.documentElement.dataset.theme === 'light' ? 'light' : 'dark');
  useEffect(() => {
    const observer = new MutationObserver(() => setTheme(document.documentElement.dataset.theme === 'light' ? 'light' : 'dark'));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    return () => observer.disconnect();
  }, []);

  const collapsed = useMemo(() => new Set(view.nodes.filter(item => item.collapsed).map(item => item.element_id)), [view]);
  const hidden = useMemo(() => {
    const result = new Set<string>();
    for (const geometry of view.nodes) {
      let parent = parentId(config, geometry.element_id);
      while (parent) { if (collapsed.has(parent)) result.add(geometry.element_id); parent = parentId(config, parent); }
    }
    return result;
  }, [config, view, collapsed]);

  useEffect(() => {
    const elements = [...config.subsystems, ...config.servers, ...config.processes];
    const ordered = [...view.nodes].sort((left, right) => {
      const depth = (id: string) => config.processes.some(item => item.id === id) ? 2 : config.servers.some(item => item.id === id) ? 1 : 0;
      return depth(left.element_id) - depth(right.element_id);
    });
    setNodes(ordered.flatMap(geometry => {
      const item = elements.find(element => element.id === geometry.element_id);
      if (!item) return [];
      const kind = kindOf(config, item.id);
      const isGroup = kind !== 'process';
      const children = view.nodes.filter(node => parentId(config, node.element_id) === item.id);
      return [{ id: item.id, type: 'topology', parentId: parentId(config, item.id), extent: parentId(config, item.id) ? 'parent' as const : undefined,
        position: { x: geometry.x, y: geometry.y }, width: geometry.width, height: isGroup && geometry.collapsed ? 58 : geometry.height,
        style: { width: geometry.width, height: isGroup && geometry.collapsed ? 58 : geometry.height }, hidden: hidden.has(item.id),
        className: highlighted.has(item.id) ? 'dependency-highlight' : '', selected: selectedIds.includes(item.id),
        draggable: editable && !saving, connectable: kind === 'process' && editable && !saving, dragHandle: isGroup ? '.node-header' : undefined,
        data: { name: item.name, kind, description: item.description, editable: editable && !saving, collapsed: geometry.collapsed,
          minWidth: Math.max(isGroup ? 280 : 220, ...children.map(node => node.x + node.width + 15)), minHeight: Math.max(isGroup ? 100 : 65, ...children.map(node => node.y + node.height + 15)),
          addChildDisabled: saving || kind === 'server' && !config.parsers?.length,
          addChildNeedsParser: kind === 'server' && !config.parsers?.length,
          onAddChild: editable && (kind === 'subsystem' || kind === 'server') ? () => onAddChild({ kind, id: item.id }) : undefined,
          onSelect: (additive?: boolean) => onSelect({ kind, id: item.id }, additive), onCollapse: () => onCollapse(item.id), onResize: (updated: { x: number; y: number; width: number; height: number }) => onGeometry(item.id, updated) },
      }];
    }));
  }, [config, view, editable, saving, selectedIds, highlighted, hidden, onSelect, onCollapse, onGeometry, onAddChild]);

  useEffect(() => {
    const frame = requestAnimationFrame(() => { void instance.current?.fitView({ padding: .12, duration: 150 }); });
    return () => cancelAnimationFrame(frame);
  }, [view.id, view.nodes.length]);

  useEffect(() => {
    if (reveal && selection && instance.current) {
      const flow = selection.kind === 'flow' ? config.flows.find(flow => flow.id === selection.id) : undefined;
      const targets = flow ? [flow.source_process_id, flow.target_process_id] : [selection.id];
      const frame = requestAnimationFrame(() => { void instance.current?.fitView({ nodes: targets.map(id => ({ id })), padding: .8, duration: 200, maxZoom: 1.3 }); });
      return () => cancelAnimationFrame(frame);
    }
  }, [reveal, selection]);

  const edges = config.flows.filter(flow => view.flow_ids.includes(flow.id)).map(flow => ({
    id: flow.id, source: flow.source_process_id, target: flow.target_process_id, label: flow.name,
    hidden: hidden.has(flow.source_process_id) || hidden.has(flow.target_process_id),
    selected: selection?.kind === 'flow' && selection.id === flow.id,
    markerEnd: { type: MarkerType.ArrowClosed, color: 'var(--si-flow)' },
    className: highlighted.has(flow.source_process_id) && highlighted.has(flow.target_process_id) ? 'dependency-edge' : '',
    style: { stroke: 'var(--si-flow)', strokeWidth: 2 }, labelStyle: { fill: 'var(--si-text)', fontSize: 11 }, labelBgStyle: { fill: 'var(--si-surface)' },
  }));
  function connect(connection: GraphConnection) { if (editable && connection.source && connection.target) onConnect(connection.source, connection.target); }
  function nodeClick(event: MouseEvent, node: DiagramNode) { onSelect({ kind: kindOf(config, node.id), id: node.id }, event.shiftKey || event.ctrlKey || event.metaKey); }
  const changeNodes = useCallback((changes: NodeChange<DiagramNode>[]) => {
    const next = applyNodeChanges(changes, nodes);
    setNodes(next);
    // Selection is synchronized only from an actual node-selection change.
    // Mirroring store selection notifications back into controlled props can
    // replay an older selection while React Flow measures replacement nodes.
    if (changes.some(change => change.type === 'select')) onMultiSelect(next.filter(node => node.selected).map(node => node.id));
  }, [nodes, onMultiSelect]);

  function persistPositions(moved: { id: string; position: { x: number; y: number } }[]) {
    if (!editable || saving || !moved.length) return;
    const positions = snapTopologyPositions(instance.current?.getNodes() ?? nodes, moved);
    if (!positions.length) return;
    setNodes(current => current.map(node => ({ ...node, position: positions.find(item => item.id === node.id)?.position ?? node.position })));
    onGeometry(positions[0].id, positions[0].position, positions);
  }

  return <div className="graph-shell"><div className="graph-navigation"><button title={t("Zoom and pan to show the whole diagram.")} onClick={() => { void instance.current?.fitView({ padding: .15, duration: 150 }); }}>{t("Fit diagram")}</button><button title={t("Zoom and pan to the selected elements.")} disabled={!selectedIds.length} onClick={() => { void instance.current?.fitView({ nodes: selectedIds.map(id => ({ id })), padding: .35, maxZoom: 1.3, duration: 150 }); }}>{t("Fit selection")}</button><span>{t("Shift + drag to select · Ctrl + scroll to zoom")}</span></div><div className="reactflow-canvas" aria-label={t("Interactive topology diagram")}>
    <ReactFlow<DiagramNode> nodes={nodes} edges={edges} nodeTypes={nodeTypes} onInit={value => { instance.current = value; }} onNodesChange={changeNodes} onNodeClick={nodeClick} onNodeDragStop={(_event, node, moved) => persistPositions(moved.length ? moved : [node])} onEdgeClick={(_event, edge) => onSelect({ kind: 'flow', id: edge.id })} onConnect={connect} nodesDraggable={editable && !saving} nodesConnectable={editable && !saving} edgesReconnectable={false} deleteKeyCode={null} selectionKeyCode="Shift" multiSelectionKeyCode={['Meta', 'Control']} selectionOnDrag snapToGrid snapGrid={TOPOLOGY_SNAP_GRID} onKeyUp={event => { if (event.key.startsWith('Arrow') && event.target instanceof HTMLElement && event.target.classList.contains('react-flow__node')) persistPositions(instance.current?.getNodes().filter(node => node.selected) ?? []); }} fitView fitViewOptions={{ padding: .12 }} minZoom={.15} maxZoom={2} colorMode={theme} ariaLabelConfig={{ 'controls.ariaLabel': t('Diagram controls'), 'controls.zoomIn.ariaLabel': t('Zoom in'), 'controls.zoomOut.ariaLabel': t('Zoom out'), 'controls.fitView.ariaLabel': t('Fit diagram'), 'controls.interactive.ariaLabel': t('Toggle diagram interaction'), 'minimap.ariaLabel': t('Diagram minimap'), 'handle.ariaLabel': t('Connection handle'), 'node.a11yDescription.default': t('Press Enter or Space to select a node. Use the arrow keys to move it. Escape cancels movement.'), 'node.a11yDescription.keyboardDisabled': t('Press Enter or Space to select a node.'), 'edge.a11yDescription.default': t('Press Enter or Space to select a flow.'), 'node.a11yDescription.ariaLiveMessage': ({ direction, x, y }) => t('Moved selected node {direction}. New position, x: {x}, y: {y}', { direction: t(direction), x, y }) }} proOptions={{ hideAttribution: false }}>
      <Controls showInteractive={false} /><MiniMap pannable zoomable maskColor="color-mix(in srgb, var(--si-canvas) 65%, transparent)" nodeColor={node => node.data.kind === 'process' ? 'var(--si-accent)' : 'var(--si-header)'} />
    </ReactFlow>
  </div></div>;
}
