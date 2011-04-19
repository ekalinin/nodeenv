.PHONY: doc deploy deploy-github deploy-pypi clean

deploy-github:
	git push --tags origin master

deploy-pypi:
	python setup.py sdist upload

deploy: deploy-github deploy-pypi

clean:
	@rm -rf nodeenv.egg-info/
	@rm -rf dist/
	@rm -rf build/
