#!/usr/bin/env node
import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const CONTRACT_DIR = path.join(ROOT, "contracts");
const SNAPSHOT_FILE = path.join(CONTRACT_DIR, "bff-schema.snapshot.json");

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf-8"));
}

function isType(value, type) {
  if (type === "string") {
    return typeof value === "string";
  }
  if (type === "number") {
    return typeof value === "number" && Number.isFinite(value);
  }
  if (type === "boolean") {
    return typeof value === "boolean";
  }
  if (type === "object") {
    return typeof value === "object" && value !== null && !Array.isArray(value);
  }
  if (type === "any") {
    return true;
  }
  if (type === "null") {
    return value === null;
  }
  return false;
}

function assertFieldType(snapshotName, fieldName, value, descriptor) {
  const expectedTypes = descriptor.split("|").map((item) => item.trim());
  const ok = expectedTypes.some((expectedType) => isType(value, expectedType));
  if (!ok) {
    throw new Error(
      `[${snapshotName}] field "${fieldName}" expected "${descriptor}" but got ${JSON.stringify(value)}`
    );
  }
}

function validateSnapshot(snapshotName, payload, schema) {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error(`[${snapshotName}] payload must be an object`);
  }
  const row = payload;
  const required = schema.required ?? {};
  const optional = schema.optional ?? {};

  for (const [fieldName, descriptor] of Object.entries(required)) {
    if (!(fieldName in row)) {
      throw new Error(`[${snapshotName}] missing required field "${fieldName}"`);
    }
    assertFieldType(snapshotName, fieldName, row[fieldName], String(descriptor));
  }

  for (const [fieldName, descriptor] of Object.entries(optional)) {
    if (!(fieldName in row)) {
      continue;
    }
    assertFieldType(snapshotName, fieldName, row[fieldName], String(descriptor));
  }
}

function run() {
  const schemaSnapshot = readJson(SNAPSHOT_FILE);
  const cases = [
    {
      file: path.join(CONTRACT_DIR, "snapshots/chat-success.json"),
      schemaKey: "chat_success_v1",
    },
    {
      file: path.join(CONTRACT_DIR, "snapshots/chat-success-v2.json"),
      schemaKey: "chat_success_v2",
    },
    {
      file: path.join(CONTRACT_DIR, "snapshots/error-rate-limited.json"),
      schemaKey: "error_envelope_v1",
    },
    {
      file: path.join(CONTRACT_DIR, "snapshots/error-service-unavailable.json"),
      schemaKey: "error_envelope_v1",
    },
  ];

  for (const testCase of cases) {
    const payload = readJson(testCase.file);
    const schema = schemaSnapshot[testCase.schemaKey];
    if (!schema) {
      throw new Error(`missing schema key: ${testCase.schemaKey}`);
    }
    validateSnapshot(path.basename(testCase.file), payload, schema);
  }

  console.log("bff contract snapshot check passed");
}

try {
  run();
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  console.error(message);
  process.exit(1);
}
