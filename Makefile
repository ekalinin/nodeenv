.PHONY: deploy deploy-github deploy-pypi update-pypi clean test

deploy-github:
	git tag `grep "nodeenv_version =" nodeenv.py | sed 's/.*= *//;s/'\'//g`
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
	@rm -rf env/
	@rm -rf nodeenv/

test:
	@rm -rf env                           && \
		virtualenv --no-site-packages env && \
		. env/bin/activate                && \
		python setup.py install           && \
		rm -rf nodeenv                    && \
		nodeenv -j 4 nodeenv

test2:
	@rm -rf env                           && \
		virtualenv --no-site-packages env && \
		. env/bin/activate                && \
		python setup.py install           && \
		nodeenv -j 4 -p
