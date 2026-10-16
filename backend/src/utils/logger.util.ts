import fs from 'fs';
import path from 'path';

export enum LogLevel {
  ERROR = 'ERROR',
  WARN = 'WARN',
  INFO = 'INFO',
  DEBUG = 'DEBUG',
}

interface LogEntry {
  timestamp: string;
  level: LogLevel;
  context: string;
  message: string;
  data?: any;
  stack?: string;
}

class Logger {
  private logDir: string;
  private logFile: string;
  private errorLogFile: string;

  constructor() {
    this.logDir = path.join(process.cwd(), 'logs');
    this.logFile = path.join(this.logDir, 'app.log');
    this.errorLogFile = path.join(this.logDir, 'error.log');
    this.ensureLogDirectory();
  }

  private ensureLogDirectory(): void {
    if (!fs.existsSync(this.logDir)) {
      fs.mkdirSync(this.logDir, { recursive: true });
    }
  }

  private formatLogEntry(entry: LogEntry): string {
    const { timestamp, level, context, message, data, stack } = entry;
    let logMessage = `[${timestamp}] [${level}] [${context}] ${message}`;
    
    if (data) {
      logMessage += `\nData: ${JSON.stringify(data, null, 2)}`;
    }
    
    if (stack) {
      logMessage += `\nStack: ${stack}`;
    }
    
    return logMessage + '\n';
  }

  private writeToFile(logMessage: string, isError: boolean = false): void {
    try {
      const targetFile = isError ? this.errorLogFile : this.logFile;
      fs.appendFileSync(targetFile, logMessage);
    } catch (error) {
      console.error('[Logger] Failed to write to log file:', error);
    }
  }

  private log(level: LogLevel, context: string, message: string, data?: any, error?: Error): void {
    const timestamp = new Date().toISOString();
    const entry: LogEntry = {
      timestamp,
      level,
      context,
      message,
      data,
      stack: error?.stack,
    };

    const formattedLog = this.formatLogEntry(entry);
    
    const isError = level === LogLevel.ERROR;
    this.writeToFile(formattedLog, isError);
    
    if (isError) {
      this.writeToFile(formattedLog, false);
    }

    const consoleMethod = isError ? console.error : level === LogLevel.WARN ? console.warn : console.log;
    const emoji = isError ? '🚨' : level === LogLevel.WARN ? '⚠️' : level === LogLevel.INFO ? '📘' : '🔍';
    consoleMethod(`${emoji} [${context}] ${message}`, data || '');
    if (error?.stack) {
      console.error(error.stack);
    }
  }

  error(context: string, message: string, error?: Error, data?: any): void {
    this.log(LogLevel.ERROR, context, message, data, error);
  }

  warn(context: string, message: string, data?: any): void {
    this.log(LogLevel.WARN, context, message, data);
  }

  info(context: string, message: string, data?: any): void {
    this.log(LogLevel.INFO, context, message, data);
  }

  debug(context: string, message: string, data?: any): void {
    if (process.env.NODE_ENV === 'development') {
      this.log(LogLevel.DEBUG, context, message, data);
    }
  }
}

export const logger = new Logger();
