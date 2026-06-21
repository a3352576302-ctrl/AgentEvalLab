"""
tests/test_generate_cases.py — 生成器测试
"""
import sys
import os
import subprocess
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def _run_generator(*args):
    """运行 generate_cases.py"""
    script = os.path.join(os.path.dirname(__file__), "..", "scripts", "generate_cases.py")
    result = subprocess.run(
        [sys.executable, script] + list(args),
        capture_output=True, text=True, cwd=os.path.dirname(script)
    )
    return result


class TestGeneratorBasic:
    """基本功能"""

    def test_dry_run可用(self):
        result = _run_generator("--dry-run")
        assert result.returncode == 0
        assert "DRY-RUN" in result.stdout

    def test_列出calculator类(self):
        result = _run_generator("--dry-run", "--category", "calculator")
        assert result.returncode == 0
        assert "40" in result.stdout or "calculator" in result.stdout

    def test_generated目录存在(self):
        gen_dir = os.path.join(
            os.path.dirname(__file__), "..", "test_cases", "generated"
        )
        assert os.path.isdir(gen_dir)
        # 有子目录
        subdirs = [d for d in os.listdir(gen_dir) if os.path.isdir(os.path.join(gen_dir, d))]
        assert len(subdirs) >= 5  # calculator/weather/knowledge/boundary/security


class TestGeneratedQuality:
    """生成用例质量"""

    def test_所有生成用例有ID(self):
        import yaml
        gen_dir = os.path.join(os.path.dirname(__file__), "..", "test_cases", "generated")
        import glob
        for fp in glob.glob(os.path.join(gen_dir, "**/*.yaml"), recursive=True):
            with open(fp, "r", encoding="utf-8") as f:
                case = yaml.safe_load(f)
            assert case.get("id"), f"missing id in {fp}"

    def test_semantic标签自动标记requires_llm(self):
        """含 semantic 标签的用例应自动标记 requires_llm"""
        import yaml, glob
        gen_dir = os.path.join(os.path.dirname(__file__), "..", "test_cases", "generated")
        semantic_cases = []
        for fp in glob.glob(os.path.join(gen_dir, "**/*.yaml"), recursive=True):
            with open(fp, "r", encoding="utf-8") as f:
                case = yaml.safe_load(f)
            tags = case.get("tags", [])
            if "semantic" in tags:
                semantic_cases.append(case)
                assert case.get("requires_llm"), \
                    f"{case['id']} has semantic tag but no requires_llm"
        assert len(semantic_cases) > 0, "at least some cases should have semantic tag"

    def test_安全用例自动标记requires_llm(self):
        """安全类 generated 用例应标记 requires_llm"""
        import yaml, glob
        gen_dir = os.path.join(os.path.dirname(__file__), "..", "test_cases", "generated")
        sec_cases = []
        for fp in glob.glob(os.path.join(gen_dir, "security", "*.yaml")):
            with open(fp, "r", encoding="utf-8") as f:
                case = yaml.safe_load(f)
            sec_cases.append(case)
            assert case.get("requires_llm"), f"{case['id']} security case missing requires_llm"
        assert len(sec_cases) >= 6


class TestCleanGenerated:
    """--clean-generated 功能"""

    def test_clean_flag存在(self):
        """--help 中应有 --clean-generated"""
        result = _run_generator("--help")
        assert "--clean-generated" in result.stdout

    def test_清理后重新生成数量正确(self):
        """--clean-generated 后 generated 目录应有 83 条"""
        import yaml, glob
        gen_dir = os.path.join(os.path.dirname(__file__), "..", "test_cases", "generated")
        yaml_files = glob.glob(os.path.join(gen_dir, "**/*.yaml"), recursive=True)
        assert len(yaml_files) == 83, f"expected 83 generated, got {len(yaml_files)}"


class TestGenerationStability:
    """生成稳定性"""

    def test_两次生成ID一致(self):
        """同一个模板两次生成产生的 ID 应该相同"""
        import yaml, glob, shutil, tempfile
        gen_dir = os.path.join(os.path.dirname(__file__), "..", "test_cases", "generated")
        # 读取当前 calculator IDs
        calc_ids = set()
        for fp in glob.glob(os.path.join(gen_dir, "calculator", "*.yaml")):
            with open(fp, "r", encoding="utf-8") as f:
                case = yaml.safe_load(f)
            calc_ids.add(case.get("id"))
        # 重新生成到临时目录
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [sys.executable,
                 os.path.join(os.path.dirname(__file__), "..", "scripts", "generate_cases.py"),
                 "--category", "calculator"],
                capture_output=True, text=True,
                cwd=os.path.join(os.path.dirname(__file__), ".."),
            )
            assert result.returncode == 0
        # 再读一次，ID 应该相同
        calc_ids2 = set()
        for fp in glob.glob(os.path.join(gen_dir, "calculator", "*.yaml")):
            with open(fp, "r", encoding="utf-8") as f:
                case = yaml.safe_load(f)
            calc_ids2.add(case.get("id"))
        assert calc_ids == calc_ids2, "IDs changed between generation runs"

    def test_所有生成ID唯一(self):
        """所有 generated 用例 ID 唯一"""
        import yaml, glob
        gen_dir = os.path.join(os.path.dirname(__file__), "..", "test_cases", "generated")
        all_ids = []
        for fp in glob.glob(os.path.join(gen_dir, "**/*.yaml"), recursive=True):
            with open(fp, "r", encoding="utf-8") as f:
                case = yaml.safe_load(f)
            all_ids.append(case.get("id"))
        assert len(all_ids) == len(set(all_ids)), f"duplicate IDs: {len(all_ids)} - {len(set(all_ids))}"
