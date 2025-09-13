manifest={
  "file_name": "Archivo128MB.txt",
  "file_size": 134217728,
  "block_size": 1048576,
  "blocks": [
    {
      "index": 0,
      "id": "00000000-00fd8f9b-3bfe-40a8-a5c9-acca45feec56",
      "size": 1048576,
      "hash": "a1b2c3d4e5f6789...",
      "path": "Archivo128MBOut/blocks/00000000-00fd8f9b-3bfe-40a8-a5c9-acca45feec56.bin"
    },
    {
      "index": 1,
      "id": "00000001-3929f41c-b031-444d-a77e-400a225633d5",
      "size": 1048576,
      "hash": "b2c3d4e5f6789a1...",
      "path": "Archivo128MBOut/blocks/00000001-3929f41c-b031-444d-a77e-400a225633d5.bin"
    },
    {
      "index": 2,
      "id": "00000002-115a4f48-1fc4-47d0-8215-5157652f6c1b",
      "size": 1048576,
      "hash": "c3d4e5f6789a1b2...",
      "path": "Archivo128MBOut/blocks/00000002-115a4f48-1fc4-47d0-8215-5157652f6c1b.bin"
    }
  ]
}
print(manifest["blocks"][0]["index"])
Plan={
  "block_size": 1048576,
  "num_blocks": 122,
  "assignments": [
    {
      "block_index": 0,
      "datanodes": ["localhost:50052", "localhost:50053"]
    },
    {
      "block_index": 1,
      "datanodes": ["localhost:50053", "localhost:50054"]
    },
    {
      "block_index": 2,
      "datanodes": ["localhost:50052", "localhost:50054"]
    }
  ]
}
for a in Plan["assignments"]:
    print(a["block_index"])
