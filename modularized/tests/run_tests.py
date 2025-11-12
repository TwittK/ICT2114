import unittest
import sys
import os
from datetime import datetime

def run_all_tests():
    """Run all test suites"""
    print("="*80)
    print("LABCOMPLY TEST SUITE")
    print("="*80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Discover and run tests
    loader = unittest.TestLoader()
    test_dir = os.path.dirname(os.path.abspath(__file__))
    suite = loader.discover(test_dir, pattern='test_*.py')
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Generate test summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    print(f"Tests run: {result.testsRun}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    
    if result.testsRun > 0:
        success_rate = ((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100)
        print(f"Success rate: {success_rate:.1f}%")
    
    if result.failures:
        print(f"\n{len(result.failures)} FAILURE(S):")
        for i, (test, traceback) in enumerate(result.failures, 1):
            print(f"{i}. {test}")
            # Print just the assertion error, not the full traceback
            error_msg = traceback.split('AssertionError: ')[-1].split('\n')[0] if 'AssertionError:' in traceback else "See details above"
            print(f"   Error: {error_msg}")
    
    if result.errors:
        print(f"\n{len(result.errors)} ERROR(S):")
        for i, (test, traceback) in enumerate(result.errors, 1):
            print(f"{i}. {test}")
            # Print just the error message
            error_lines = traceback.split('\n')
            error_msg = next((line for line in error_lines if 'Error:' in line or 'Exception:' in line), "See details above")
            print(f"   Error: {error_msg}")
    
    print(f"\nCompleted at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    return result.wasSuccessful()

if __name__ == '__main__':
    success = run_all_tests()
    if success:
        print("\n✅ All tests passed!")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed!")
        sys.exit(1)