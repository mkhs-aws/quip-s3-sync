#!/usr/bin/env python3
"""
Convenience script to run the Quip-S3 sync locally with .env file support

This script loads environment variables from a .env file and then runs the local_runner.

Usage:
    1. Copy .env.example to .env
    2. Fill in your actual values in .env
    3. Run: python run_local.py

Or run directly with environment variables:
    python local_runner.py
"""

import os
import sys
import subprocess


def load_env_file(env_file='.env'):
    """
    Load environment variables from a .env file
    """
    if not os.path.exists(env_file):
        print(f"❌ Environment file '{env_file}' not found.")
        print("📝 Please copy .env.example to .env and fill in your values:")
        print("   cp .env.example .env")
        print("   # Edit .env with your actual values")
        return False
    
    print(f"📁 Loading environment from {env_file}")
    
    with open(env_file, 'r') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                continue
            
            # Parse KEY=VALUE format
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                
                # Remove quotes if present
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                
                # Set environment variable
                os.environ[key] = value
            else:
                print(f"⚠️  Warning: Invalid line {line_num} in {env_file}: {line}")
    
    return True


def main():
    """
    Main function
    """
    print("🔧 Quip-S3 Sync Local Development Runner")
    print("=" * 45)
    
    # Try to load .env file
    if not load_env_file():
        sys.exit(1)
    
    print("✅ Environment loaded successfully")
    print()
    
    # Run the local runner
    try:
        # Import and run the local runner
        import local_runner
        local_runner.main()
    except ImportError:
        print("❌ Could not import local_runner.py")
        print("Make sure you're running this from the project root directory.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error running local runner: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()