export function startServer(): void {
  console.log("[server] listening on port 8080");
}

export function handleRequest(path: string): void {
  console.log(`[server] handling request: ${path}`);
}
