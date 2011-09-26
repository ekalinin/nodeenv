.PHONY: deploy deploy-github deploy-pypi update-pypi clean

deploy-github:
	git tag `grep "nodeenv_version =" nodeenv.py | grep -o -E '[0-9]\.[0-9]\.[0-9]'`
	git push --tags origin master

deploy-pypi:
	python setup.py sdist upload

update-pypi:
	python setup.py register

deploy: deploy-github deploy-pypi

clean:
	@rm -rf nodeenv.egg-info/
	@rm -rf dist/
	@rm -rf build/
