import pytest
import sys
import io
import requests
sys.path.append('../backend')
import main


@pytest.fixture()
def app():
    main.app.config.update({
        "TESTING": True,
    })
    yield main.app


@pytest.fixture()
def client(app):
    return main.app.test_client()


@pytest.fixture()
def runner(app):
    return main.app.test_cli_runner()


# * Test home page
def test_show_home_page(client):
    response = client.get("/")
    assert response.status_code == 200


# * Test add page
def test_show_add_page(client):
    response = client.get("/add")
    assert response.status_code == 200


def test_adding_image(client):
    response = client.post("/add", data={
        "hash": "123",
        "image": (io.BytesIO(b"some initial text data"), 'test.jpeg')
    }, content_type='multipart/form-data')
    assert response.status_code == 201


# * Test get page
def test_show_get_page(client):
    response = client.get("/get")
    assert response.status_code == 200


def test_get_success(client):
    response = client.post("/get", data={
        "hash": "1"
    })
    assert response.status_code == 200


def test_get_failure(client):
    response = client.post("/get", data={
        "hash": "11"
    })
    assert response.status_code == 404


# * Test keys page
def test_show_keys_page(client):
    response = client.get("/keys")
    assert response.status_code == 200


# * Test control page
def test_show_control_page(client):
    response = client.get("/control")
    assert response.status_code == 200


def test_setting_size_and_policy(client):
    response = client.post("/control", data={
        "cache-size": 15,
        "replace-policy": 1
    })
    assert response.status_code == 200
    assert int(main.cache.getSize()) == 15
    assert main.cache.getReplacePolicy() == "RANDOM"


# * Test statistics page
def test_show_statistics_page(client):
    response = client.get("/statistics")
    assert response.status_code == 200


# * Test cache keys page
def test_show_cache_keys_page(client):
    response = client.get("/cache/keys")
    assert response.status_code == 200


# * Test cache clear
def test_clear_cache_cleared(client):
    # Add image to cache
    response = client.post("/get", data={
        "hash": "1"
    })
    assert response.status_code == 200
    assert main.cache.getUsedSpace() != 0

    # Clear cache
    response = client.post("/clear")
    assert response.status_code == 200
    assert main.cache.getUsedSpace() == 0