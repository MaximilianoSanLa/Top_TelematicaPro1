const fs = require('fs');
const path = require('path');
const os = require('os');
const { exec } = require('child_process');
const { Kafka } = require('kafkajs');
const axios = require('axios');

// Kafka setup
const kafka = new Kafka({
  clientId: `worker-${os.hostname()}`,
  brokers: ['44.217.41.36:9092'] // replace with broker's PRIVATE IP if on same VPC
});

const consumer = kafka.consumer({ groupId: `worker-${os.hostname()}` });

const producer = kafka.producer();

// Folder where user data is stored
const WORKER_DIR = path.join(__dirname, 'worker_data');
if (!fs.existsSync(WORKER_DIR)) {
  fs.mkdirSync(WORKER_DIR, { recursive: true });
}

// Helper: ensure user folder exists
function ensureUserDir(authKey) {
  const userDir = path.join(WORKER_DIR, authKey);
  if (!fs.existsSync(userDir)) {
    fs.mkdirSync(userDir, { recursive: true });
  }
  return userDir;
}

// Get worker public IP
async function getPublicIP() {
  try {
    const res = await axios.get('https://api.ipify.org?format=json');
    return res.data.ip;
  } catch (e) {
    return 'unknown';
  }
}

async function run() {
  await consumer.connect();
  await producer.connect();
  await consumer.subscribe({ topic: 'commands', fromBeginning: false });

  console.log('✅ Worker listening for commands...');

  await consumer.run({
    eachMessage: async ({ message }) => {
      try {
        const data = JSON.parse(message.value.toString());
        const { authKey, cmd } = data;

        if (!authKey || !cmd) {
          console.log('❌ Invalid message received:', data);
          return;
        }

        // Ensure user folder exists
        const userDir = ensureUserDir(authKey);

        // Execute command in user's folder
        exec(cmd, { cwd: userDir }, async (err, stdout, stderr) => {
          const output = err ? stderr : stdout;

          const workerIP = await getPublicIP();
          const result = {
            authKey,
            worker: workerIP,
            cmd,
            output: output.trim()
          };

          // Send result back to broker
          await producer.send({
            topic: 'results',
            messages: [{ value: JSON.stringify(result) }]
          });

          console.log(`📤 Sent result from worker ${workerIP}`, result);
        });
      } catch (err) {
        console.error('❌ Worker failed to process message:', err);
      }
    }
  });
}

run().catch(console.error);
