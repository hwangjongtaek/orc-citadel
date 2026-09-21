const COMPONENT_TARGETS = new Map([
  ['grafana', {port: 3000, path: '/d/citadel-pipeline'}],
  ['duckdb-ui', {port: 4213, path: '/'}],
  ['neo4j', {port: 7474, path: '/'}],
  ['minio', {port: 9001, path: '/'}],
  ['opensearch', {port: 9200, path: '/_cluster/health?pretty'}],
]);

export function buildComponentLink(component, currentLocation) {
  if (!component?.reachable) return null;

  const target = COMPONENT_TARGETS.get(component.id);
  if (!target) return null;

  const isDuckDbUi = component.id === 'duckdb-ui';
  const protocol = isDuckDbUi ? 'http:' : currentLocation.protocol;
  const hostname = isDuckDbUi ? 'localhost' : currentLocation.hostname;
  return `${protocol}//${hostname}:${target.port}${target.path}`;
}
