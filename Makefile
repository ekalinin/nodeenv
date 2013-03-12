.PHONY: deploy deploy-github deploy-pypi update-pypi clean test

deploy-github:
	git tag `grep "nodeenv_version =" nodeenv.py | grep -o -E '[0-9]\.[0-9]\.[0-9]{1,2}'`
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
