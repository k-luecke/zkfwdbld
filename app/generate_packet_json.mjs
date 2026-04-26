import { writePacketSnapshot } from "./packet_snapshot.mjs";

const packetDir = process.argv[2];
const outputPath = process.argv[3];
const result = writePacketSnapshot({ packetDir, outputPath });

console.log(
  JSON.stringify(
    {
      ok: true,
      output_path: result.outputPath,
      packet_type: result.packet.packet_type,
      generated_at: result.packet.generated_at
    },
    null,
    2
  )
);
