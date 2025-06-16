build:
	python3 -m build
upload_to_pypi: build
	python3 -m twine upload --repository pypi dist/*
