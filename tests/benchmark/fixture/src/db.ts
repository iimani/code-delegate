export function connect(): void {
  console.log("[db] connecting to database");
}

export function query(sql: string): void {
  console.log(`[db] running query: ${sql}`);
}
