src-deploy:
	git push --tags origin master

pypi-deploy:
	python setup.py sdist upload

deploy: src-deploy pypi-deploy

clean:
	@rm -rf nodeenv.egg-info/
	@rm -rf dist/
	@rm -rf build/
