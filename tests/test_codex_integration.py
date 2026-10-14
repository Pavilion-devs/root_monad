import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('codex_launcher',ROOT/'integrations/codex/chat.py')
launcher=importlib.util.module_from_spec(spec);spec.loader.exec_module(launcher)

class CodexIntegrationTests(unittest.TestCase):
    def test_read_check_exposes_only_read_and_has_no_owner_profile(self):
        settings=launcher.settings(True)
        self.assertEqual(settings['mcp_servers.portable_memory.enabled_tools'],['memory_current'])
        args=settings['mcp_servers.portable_memory.args']
        self.assertEqual(Path(args[-1]).parent.name,'codex')
        for feature in ('shell_tool','apps','plugins','hooks','multi_agent'):
            self.assertFalse(settings['features.'+feature])
    def test_proposals_need_explicit_launcher_option_and_never_owner_tools(self):
        self.assertEqual(launcher.settings(False)['mcp_servers.portable_memory.enabled_tools'],['memory_current','memory_propose'])
    def test_credentials_do_not_leak_to_child_environment(self):
        with patch.dict(os.environ,{'ANTHROPIC_API_KEY':'secret','OPENAI_API_KEY':'secret','PRIVATE_KEY':'secret'}):
            env=launcher.environment()
        self.assertNotIn('ANTHROPIC_API_KEY',env)
        self.assertNotIn('OPENAI_API_KEY',env)
        self.assertNotIn('PRIVATE_KEY',env)
    def test_exec_is_fresh_read_only_and_ignores_unrelated_user_config(self):
        command=launcher.arguments('/tmp/empty-memory-test',True)
        for flag in ('--ignore-user-config','--ignore-rules','--ephemeral','--json'):
            self.assertIn(flag,command)
        self.assertEqual(command[command.index('--sandbox')+1],'read-only')
        self.assertEqual(command[command.index('-C')+1],'/tmp/empty-memory-test')

if __name__=='__main__':unittest.main()
