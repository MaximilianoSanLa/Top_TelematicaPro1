const { Kafka } = require('kafkajs');
const express = require('express');
const bodyParser = require('body-parser');
const fs = require('fs');
const path = require('path');

const app = express();
app.use(bodyParser.json());

const kafka = new Kafka({
  clientId: 'api',
  brokers: ['44.217.41.36:9092'] // change to your broker IP
});

const producer = kafka.producer();
const consumer = kafka.consumer({ groupId: 'api-group' });

// store results
let results = {};
const USERS_DIR = path.join(__dirname, 'users');
if (!fs.existsSync(USERS_DIR)) fs.mkdirSync(USERS_DIR);

// helper to persist users
function getUser(username) {
  const userFile = path.join(USERS_DIR, `${username}.json`);
  if (!fs.existsSync(userFile)) return null;
  return JSON.parse(fs.readFileSync(userFile, 'utf-8'));
}

function saveUser(user) {
  const userFile = path.join(USERS_DIR, `${user.username}.json`);
  fs.writeFileSync(userFile, JSON.stringify(user, null, 2));
}

async function run() {
  await producer.connect();
  await consumer.connect();
  await consumer.subscribe({ topic: 'results', fromBeginning: true });

  await consumer.run({
    eachMessage: async ({ message }) => {
      try {
        const data = JSON.parse(message.value.toString());
        const authKey = data.authKey;

        if (!results[authKey]) results[authKey] = [];
        results[authKey].push(data); // includes worker IP + output
      } catch (err) {
        console.error('Error parsing worker result:', err);
      }
    }
  });
}
run().catch(console.error);

// ---------------- API ROUTES ----------------

// superuser creates new user
app.post('/superuser/create', (req, res) => {
  const { superKey, username, password } = req.body;
  if (superKey !== 'my-secret-superuser-key') {
    return res.status(403).json({ error: 'Forbidden' });
  }
  if (getUser(username)) {
    return res.status(400).json({ error: 'User already exists' });
  }
  const authKey = Math.random().toString(36).substring(2, 12);
  const user = { username, password, authKey };
  saveUser(user);
  res.json({ status: 'User created', username, authKey });
});

// login
app.post('/login', (req, res) => {
  const { username, password } = req.body;
  const user = getUser(username);
  if (!user || user.password !== password) {
    return res.status(401).json({ error: 'Invalid credentials' });
  }
  res.json({ authKey: user.authKey });
});

// send command
app.post('/command', async (req, res) => {
  const { authKey, cmd } = req.body;
  if (!authKey || !cmd) {
    return res.status(400).json({ error: 'Missing authKey or cmd' });
  }

  // validate authKey (skip directories, only read JSON files)
  const userFiles = fs.readdirSync(USERS_DIR);
  let valid = false;
  for (const file of userFiles) {
    const fullPath = path.join(USERS_DIR, file);
    const stat = fs.statSync(fullPath);

    if (stat.isFile() && file.endsWith('.json')) {
      const user = JSON.parse(fs.readFileSync(fullPath, 'utf-8'));
      if (user.authKey === authKey) {
        valid = true;
        break;
      }
    }
  }

  if (!valid) {
    return res.status(401).json({ error: 'User not found' });
  }

  results[authKey] = [];

  await producer.send({
    topic: 'commands',
    messages: [
      { value: JSON.stringify({ authKey, cmd }) }
    ]
  });

  // wait for workers to respond
  setTimeout(() => {
    res.json({
      cmd,
      results: results[authKey] || []  // now includes worker IP + output
    });
  }, 2000);
});

app.listen(3000, () => console.log('API running on port 3000'));
