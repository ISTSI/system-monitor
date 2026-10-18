// Canvas units at 100% zoom: roughly one lowercase letter in the UI font.
export const TOPOLOGY_SNAP_GRID: [number, number] = [8, 8];

type Point = { x: number; y: number };
type PositionedNode = { id: string; parentId?: string; position: Point; width?: number; height?: number };

export function snapTopologyPositions(nodes: PositionedNode[], moved: { id: string; position: Point }[]): { id: string; position: Point }[] {
  const lookup = new Map(nodes.map(node => [node.id, { ...node, position: { ...node.position } }]));
  for (const node of moved) {
    const current = lookup.get(node.id);
    if (current) current.position = { ...node.position };
  }
  const depth = (id: string): number => {
    const parent = lookup.get(id)?.parentId;
    return parent ? depth(parent) + 1 : 0;
  };
  const absolute = (id?: string): Point => {
    const node = id ? lookup.get(id) : undefined;
    if (!node) return { x: 0, y: 0 };
    const parent = absolute(node.parentId);
    return { x: parent.x + node.position.x, y: parent.y + node.position.y };
  };
  const snap = (value: number, step: number, min: number, max: number) => {
    const lower = Math.ceil(min / step) * step;
    const upper = Math.max(lower, Math.floor(max / step) * step);
    return Math.min(upper, Math.max(lower, Math.round(value / step) * step));
  };
  // Parents first: nested coordinates are relative, but every dragged origin
  // belongs to the same canvas grid, including in legacy off-grid layouts.
  return [...moved].sort((left, right) => depth(left.id) - depth(right.id)).flatMap(item => {
    const node = lookup.get(item.id);
    if (!node) return [];
    const parent = node.parentId ? lookup.get(node.parentId) : undefined;
    const origin = absolute(node.parentId);
    const point = absolute(node.id);
    node.position = {
      x: snap(point.x, TOPOLOGY_SNAP_GRID[0], parent ? origin.x + 10 : -Infinity, parent ? origin.x + (parent.width ?? Infinity) - (node.width ?? 0) : Infinity) - origin.x,
      y: snap(point.y, TOPOLOGY_SNAP_GRID[1], parent ? origin.y + 50 : -Infinity, parent ? origin.y + (parent.height ?? Infinity) - (node.height ?? 0) : Infinity) - origin.y,
    };
    return [{ id: node.id, position: node.position }];
  });
}
