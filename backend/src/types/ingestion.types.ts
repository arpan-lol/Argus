export const INGESTION_STAGE_IDS = ["parse", "normalize", "chunk", "embed", "extract", "resolve", "index"] as const;

export type IngestionStageId = typeof INGESTION_STAGE_IDS[number];
export type IngestionStatus = "queued" | "running" | "complete" | "failed" | "waiting_configuration" | "skipped";
export type SourceCapability = "original_available" | "parsed_text" | "chunk_navigation" | "fulltext_search" | "vector_search" | "entity_navigation" | "relationship_navigation";
export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

export interface SourceIdentity {
  sourceId: string;
  originalFilename: string;
  mediaType: string;
  byteLength: number;
  receivedAt: string;
  origin: { kind: "upload" | "remote" | "import"; locator?: string; externalId?: string };
}

export interface SourceRevision {
  sourceId: string;
  sourceRevision: string;
  contentDigest: { algorithm: string; value: string };
  originalArtifactId: string;
  createdAt: string;
  supersedesRevision?: string;
}

export interface ProcessingVersion {
  processingVersion: string;
  contractVersion: string;
  configurationDigest: { algorithm: string; value: string };
  createdAt: string;
  stageVersions: Record<IngestionStageId, string>;
}

export interface ProcessingScope {
  sourceId: string;
  sourceRevision: string;
  processingVersion: string;
}

export interface ProcessorMetadata {
  adapter: string;
  adapterVersion: string;
  provider?: string;
  model?: string;
  modelVersion?: string;
  dimensions?: number;
  promptVersion?: string;
  parameters?: Record<string, JsonValue>;
}

export interface IngestionIssue {
  code: string;
  message: string;
  recoverable: boolean;
  retryAction: "retry_stage" | "change_configuration" | "replace_source" | "none";
  details?: Record<string, JsonValue>;
}

export interface StageArtifact {
  artifactId: string;
  kind: string;
  digest: { algorithm: string; value: string };
  producedByAttemptId: string;
}

export interface IngestionStageAttempt extends ProcessingScope {
  attemptId: string;
  jobId: string;
  stageId: IngestionStageId;
  attempt: number;
  idempotencyKey: string;
  inputFingerprint: string;
  status: IngestionStatus;
  queuedAt: string;
  startedAt?: string;
  finishedAt?: string;
  durationMs?: number;
  inputCounts: Record<string, number>;
  outputCounts: Record<string, number>;
  processors: ProcessorMetadata[];
  inputArtifactIds: string[];
  outputArtifacts: StageArtifact[];
  warnings: IngestionIssue[];
  error?: IngestionIssue;
  statusReason?: string;
  supersedesAttemptId?: string;
}

export interface SourceCapabilityState {
  capability: SourceCapability;
  status: "available" | "unavailable" | "stale";
  supportingAttemptIds: string[];
  updatedAt: string;
  reason?: string;
}

export interface IngestionJob extends ProcessingScope {
  jobId: string;
  status: IngestionStatus;
  createdAt: string;
  updatedAt: string;
  finishedAt?: string;
  currentStageId?: IngestionStageId;
  stages: Record<IngestionStageId, IngestionStageAttempt[]>;
  capabilities: SourceCapabilityState[];
  statusReason?: string;
}

export interface IngestionEvent extends ProcessingScope {
  eventId: string;
  jobId: string;
  sequence: number;
  occurredAt: string;
  kind: "job_created" | "stage_status_changed" | "stage_progress" | "artifact_published" | "capability_changed" | "job_status_changed";
  stageId?: IngestionStageId;
  attemptId?: string;
  status?: IngestionStatus;
  counts?: Record<string, number>;
  durationMs?: number;
  processors?: ProcessorMetadata[];
  issue?: IngestionIssue;
  message?: string;
  artifactIds?: string[];
  capabilityState?: SourceCapabilityState;
}

export interface TextRange {
  textArtifactId: string;
  offsetUnit: "unicode_code_point" | "utf16_code_unit";
  start: number;
  endExclusive: number;
}

export interface SourceLocation {
  originalArtifactId: string;
  textRange?: TextRange;
  pageNumber?: number;
  boundingBox?: {
    x: number;
    y: number;
    width: number;
    height: number;
    units: "normalized" | "pixels" | "points";
    origin: "top_left" | "bottom_left";
    pageWidth: number;
    pageHeight: number;
  };
  sheetName?: string;
  cellRange?: string;
  slideNumber?: number;
  structuralPath?: string;
}

export interface SourceTextMapping {
  normalizedRange: TextRange;
  sourceLocations: SourceLocation[];
  fidelity: "exact" | "derived" | "ocr";
}

export interface SourceBlock extends ProcessingScope {
  blockId: string;
  kind: "heading" | "paragraph" | "list" | "table" | "image" | "code" | "other";
  ordinal: number;
  parentBlockId?: string;
  text?: string;
  textRange?: TextRange;
  sourceLocations: SourceLocation[];
  mappings: SourceTextMapping[];
  structuredArtifactIds: string[];
  parserAttemptId: string;
  normalizationAttemptId?: string;
}

export interface SourceSpan extends ProcessingScope {
  spanId: string;
  blockIds: string[];
  range: TextRange;
  quote: string;
  sourceLocations: SourceLocation[];
  validation: "exact_match" | "unverified" | "mismatch";
}

export interface IngestionChunk extends ProcessingScope {
  chunkId: string;
  ordinal: number;
  text: string;
  blockIds: string[];
  sourceSpanIds: string[];
  parentChunkId?: string;
  sectionBlockIds: string[];
  tokenCount?: number;
  chunkAttemptId: string;
}

export interface SourceSupport extends ProcessingScope {
  chunkId: string;
  spanIds: string[];
}

export interface ExtractionConfidence {
  value: number;
  method: string;
  calibrated: boolean;
}

export interface ExtractedEntity extends ProcessingScope {
  entityId: string;
  label: string;
  type: string;
  properties: Record<string, JsonValue>;
  aliases: string[];
  supports: SourceSupport[];
  extractionAttemptId: string;
  confidence?: ExtractionConfidence;
}

export interface ExtractedRelationship extends ProcessingScope {
  relationshipId: string;
  subjectEntityId: string;
  objectEntityId: string;
  predicate: string;
  properties: Record<string, JsonValue>;
  supports: SourceSupport[];
  extractionAttemptId: string;
  confidence?: ExtractionConfidence;
}

export interface EntityResolution extends ProcessingScope {
  resolutionId: string;
  entityId: string;
  status: "resolved" | "unresolved" | "ambiguous";
  canonicalEntityId?: string;
  candidateEntityIds: string[];
  aliases: string[];
  decisionBasis: "identifier" | "rule" | "model" | "user";
  rationale: string;
  resolutionAttemptId: string;
  confidence?: ExtractionConfidence;
}
