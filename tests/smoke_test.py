import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.app.config import load_config


def test_config_loading():
    print("Testing config loading...")
    config = load_config()
    print(f"  Data dir: {config.data_dir}")
    print(f"  Smart Plug enabled: {config.smart_plug.enabled}")
    assert config.smart_plug.version == 3.3
    print("✅ Config loaded successfully")


def test_smart_plug_import():
    print("Testing Smart Plug import...")
    import backend.app.smart_plug as sp

    # Check that SmartPlugConfig is NOT in smart_plug module (should be imported)
    assert hasattr(sp, "SmartPlugConfig")
    print("✅ Smart Plug module valid")


if __name__ == "__main__":
    try:
        test_config_loading()
        test_smart_plug_import()
        print("\n🎉 Smoke tests passed!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
