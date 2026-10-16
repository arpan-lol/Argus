export class AppError extends Error {
  public readonly statusCode: number;
  public readonly shouldExposeToClient: boolean;
  public readonly clientMessage?: string;

  constructor(message: string, statusCode = 500, shouldExposeToClient = false, clientMessage?: string) {
    super(message);
    this.statusCode = statusCode;
    this.shouldExposeToClient = shouldExposeToClient;
    this.clientMessage = clientMessage;
    Object.setPrototypeOf(this, AppError.prototype);
  }
}
