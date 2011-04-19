.PHONY: doc deploy deploy-github deploy-pypi clean

doc:
	python setup.py build_sphinx

deploy-github:
	git push --tags origin master

deploy-pypi: doc
	python setup.py sdist upload
	python setup.py upload_docs --upload-dir=build/sphinx/html

deploy: deploy-github deploy-pypi

clean:
	@rm -rf nodeenv.egg-info/
	@rm -rf dist/
	@rm -rf build/
