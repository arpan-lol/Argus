FROM node:22-slim@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392

ENV NEXT_TELEMETRY_DISABLED=1

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend ./
RUN npm run build

EXPOSE 3001
CMD ["npm", "run", "start", "--", "-H", "0.0.0.0"]
