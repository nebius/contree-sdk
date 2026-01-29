from tests.e2e.sdk.run.test_for_mini_swe_agent import (
    test_thread_pool_create_run_same_client as _test_thread_pool_create_run_same_client,
)


def test_thread_pool_create_run_same_client(fake_contree_s, image_tag, api_fake_thread_pool):
    _test_thread_pool_create_run_same_client(fake_contree_s, image_tag)
