const express = require('express')
const { Kafka } = require('kafkajs')

const kafka = new Kafka({
  clientId: 'api',
  brokers: ['44.217.41.36:9092']
})

const producer = kafka.producer()
const consumer = kafka.consumer({ groupId: 'api-listener' })

const app = express()
app.use(express.json())

let responses = []

app.post('/command', async (req, res) => {
  const { command } = req.body
  responses = [] // reset

  // send command to consumers
  await producer.send({
    topic: 'commands',
    messages: [{ value: command }]
  })

  // wait 5s for workers to respond
  setTimeout(() => {
    res.json({ command, responses })
  }, 5000)
})

async function run() {
  await producer.connect()
  await consumer.connect()
  await consumer.subscribe({ topic: 'results', fromBeginning: false })

  consumer.run({
    eachMessage: async ({ message }) => {
      const result = JSON.parse(message.value.toString())
      responses.push(result)
    },
  })
}

run().catch(console.error)

app.listen(3000, () => console.log('API running on port 3000'))
