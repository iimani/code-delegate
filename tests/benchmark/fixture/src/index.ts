import { connect } from "./db";
import { startServer } from "./server";

console.log("[boot] starting application");
connect();
startServer();
