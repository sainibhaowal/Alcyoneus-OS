# Copyright 2026 Alcyoneus Authors

import unittest

from alcyoneus import (
    Video,
    Document,
    Audio,
    Image,
    SlashCommand,
    BuiltinSlashCommandName,
)


class TestPrimitives(unittest.TestCase):

    def test_primitives_media(self):
        img = Image.from_bytes(b"fake-png-bytes", mime_type="image/png")
        self.assertEqual(img.mime_type, "image/png")
        self.assertEqual(img.data, b"fake-png-bytes")

        vid = Video.from_bytes(b"fake-mp4-bytes", mime_type="video/mp4")
        self.assertEqual(vid.kind, "video")
        self.assertEqual(vid.mime_type, "video/mp4")

        doc = Document.from_bytes(b"fake-pdf-bytes", mime_type="application/pdf")
        self.assertEqual(doc.kind, "document")

    def test_slash_command_primitive(self):
        cmd = SlashCommand(name=BuiltinSlashCommandName.PLAN, command="build state graph")
        self.assertEqual(cmd.full_command, "/plan build state graph")

        cmd2 = SlashCommand(name="custom", command="args")
        self.assertEqual(cmd2.full_command, "/custom args")


if __name__ == "__main__":
    unittest.main()
