#!/usr/bin/env python3
"""Test script to verify APIs work correctly."""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


async def test_mojang_api():
    """Test Mojang API for Vanilla versions."""
    from src.engines.vanilla import VanillaEngine
    
    print("🔍 Testing Mojang API...")
    engine = VanillaEngine()
    
    versions = await engine.get_versions()
    print(f"   ✅ Found {len(versions)} Vanilla versions")
    
    latest = await engine.get_latest_version()
    print(f"   ✅ Latest version: {latest.version if latest else 'N/A'}")
    
    return True


async def test_forge_api():
    """Test Forge API."""
    from src.engines.forge import ForgeEngine
    
    print("🔍 Testing Forge API...")
    engine = ForgeEngine()
    
    versions = await engine.get_versions()
    print(f"   ✅ Found {len(versions)} Forge versions")
    
    latest = await engine.get_latest_version()
    print(f"   ✅ Latest version: {latest.version if latest else 'N/A'}")
    
    # Test recommended for specific MC version
    recommended = await engine.get_recommended_for_mc("1.20.1")
    print(f"   ✅ Recommended for 1.20.1: {recommended or 'N/A'}")
    
    return True


async def test_modrinth_api():
    """Test Modrinth API for mods."""
    from src.mods.modrinth_api import ModrinthAPI
    
    print("🔍 Testing Modrinth API...")
    
    async with ModrinthAPI() as api:
        # Search for popular mod
        mods = await api.search_mods("jei", loader="forge", game_version="1.20.1")
        print(f"   ✅ Found {len(mods)} mods for 'jei'")
        
        if mods:
            mod = mods[0]
            print(f"   ✅ Top result: {mod.title} ({mod.downloads:,} downloads)")
            
            # Get versions
            versions = await api.get_mod_versions(mod.slug, loader="forge", game_version="1.20.1")
            print(f"   ✅ Found {len(versions)} compatible versions")
    
    return True


async def test_java():
    """Test Java installation."""
    from src.utils.java import check_java, get_min_java_version
    
    print("🔍 Testing Java...")
    
    java_info = await check_java()
    if java_info.is_valid:
        print(f"   ✅ Java {java_info.version} at {java_info.path}")
        print(f"   ✅ Major version: {java_info.major_version}")
    else:
        print(f"   ❌ Java not found: {java_info.error}")
        return False
    
    # Check requirements for different MC versions
    for mc_ver in ["1.16.5", "1.18.2", "1.20.1", "1.21.1"]:
        min_java = get_min_java_version(mc_ver)
        status = "✅" if java_info.major_version >= min_java else "⚠️"
        print(f"   {status} MC {mc_ver} requires Java {min_java}")
    
    return True


async def test_config():
    """Test configuration loading."""
    from src.utils.config import load_config
    
    print("🔍 Testing Config...")
    
    try:
        config = load_config()
        print(f"   ✅ Config loaded")
        print(f"   ✅ Servers dir: {config.paths.servers_dir}")
        print(f"   ✅ Backups dir: {config.paths.backups_dir}")
        print(f"   ✅ Language: {config.language}")
        
        if config.telegram.bot_token:
            print(f"   ✅ Bot token configured")
        else:
            print(f"   ⚠️ Bot token not set (set BOT_TOKEN env or in config.yaml)")
        
        if config.telegram.admin_ids:
            print(f"   ✅ Admin IDs: {config.telegram.admin_ids}")
        else:
            print(f"   ⚠️ No admin IDs configured")
            
    except Exception as e:
        print(f"   ❌ Config error: {e}")
        return False
    
    return True


async def test_database():
    """Test database operations."""
    from src.storage.database import Database
    from src.storage.models import UserRole
    from pathlib import Path
    import tempfile
    
    print("🔍 Testing Database...")
    
    # Use temp database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)
        
        try:
            await db.connect()
            print(f"   ✅ Database connected")
            
            # Test user operations
            user = await db.get_or_create_user(123456789, "testuser")
            print(f"   ✅ User created: {user.username}")
            
            await db.set_user_role(123456789, UserRole.ADMIN)
            user = await db.get_user(123456789)
            print(f"   ✅ Role updated: {user.role.value}")
            
            # Test server list (should be empty)
            servers = await db.get_all_servers()
            print(f"   ✅ Servers in DB: {len(servers)}")
            
            await db.close()
            print(f"   ✅ Database closed")
            
        except Exception as e:
            print(f"   ❌ Database error: {e}")
            return False
    
    return True


async def test_translations():
    """Test i18n translations."""
    from src.i18n import t, get_translator
    
    print("🔍 Testing Translations...")
    
    translator = get_translator()
    print(f"   ✅ Available languages: {translator.available_languages}")
    
    # Test some translations
    tests = [
        ("bot.welcome", "ru"),
        ("bot.welcome", "en"),
        ("server.started", "ru"),
        ("button.start", "en"),
    ]
    
    for key, lang in tests:
        text = t(key, lang, name="Test")
        preview = text[:50].replace("\n", " ") + "..." if len(text) > 50 else text.replace("\n", " ")
        print(f"   ✅ [{lang}] {key}: {preview}")
    
    return True


async def main():
    """Run all tests."""
    print("=" * 50)
    print("🧪 Minecraft Server Manager - API Tests")
    print("=" * 50)
    print()
    
    tests = [
        ("Config", test_config),
        ("Java", test_java),
        ("Database", test_database),
        ("Translations", test_translations),
        ("Mojang API", test_mojang_api),
        ("Forge API", test_forge_api),
        ("Modrinth API", test_modrinth_api),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = await test_func()
            results.append((name, result))
        except Exception as e:
            print(f"   ❌ Error: {e}")
            results.append((name, False))
        print()
    
    # Summary
    print("=" * 50)
    print("📊 Summary")
    print("=" * 50)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {status}: {name}")
    
    print()
    print(f"   Result: {passed}/{total} tests passed")
    
    return all(r for _, r in results)


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

