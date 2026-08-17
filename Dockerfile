FROM node:20-alpine

WORKDIR /app

# Install build dependencies if needed
COPY package*.json ./
RUN npm install --production

# Copy application source
COPY . .

# Create persistent storage & data directories
RUN mkdir -p /app/storage /app/data /app/data/trash

EXPOSE 3000

ENV NODE_ENV=production
ENV PORT=3000

CMD ["node", "server.js"]
