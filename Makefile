.PHONY: default deploy deploy-github deploy-pypi update-pypi clean tests

default:
	: do nothing when dpkg-buildpackage runs this project Makefile

deploy-github:
	git tag `grep "nodeenv_version =" nodeenv.py | grep -o -E '[0-9]\.[0-9]{1,2}\.[0-9]{1,2}'`
	git push --tags origin master

deploy-pypi:
	python setup.py sdist upload

update-pypi:
	python setup.py register

deploy: contributors deploy-github deploy-pypi

clean:
	@rm -rf nodeenv.egg-info/
	@rm -rf dist/
	@rm -rf build/
	@rm -rf env/
	@rm -rf nodeenv/

test1:
	@echo " * test1: separate nodejs's env"
	@rm -rf env                           && \
		virtualenv --no-site-packages env && \
		. env/bin/activate                && \
		python setup.py install           && \
		rm -rf nodeenv                    && \
		nodeenv -j 4 nodeenv

test2:
	@echo " * test2: the same virtualenv's env, with 4 jobs"
	@rm -rf env                           && \
		virtualenv --no-site-packages env && \
		. env/bin/activate                && \
		python setup.py install           && \
		nodeenv -j 4 -p

test3:
	@echo " * test3: the same virtualenv's env, without any params"
	@rm -rf env                           && \
		virtualenv --no-site-packages env && \
		. env/bin/activate                && \
		python setup.py install           && \
		nodeenv -p

# https://github.com/ekalinin/nodeenv/issues/43
test4:
	@echo " * test4: separate nodejs's env for python3.4"
	@rm -rf env                                                 && \
		virtualenv --no-site-packages --python=python3.4 env    && \
		. env/bin/activate                                      && \
		python setup.py install                                 && \
		nodeenv 4 -p --prebuilt                                 && \
		nodeenv -p --node=system

test5:
	@echo " * test5: prebuilt nodejs's env for python2"
	@rm -rf env                                 && \
		virtualenv --no-site-packages env       && \
		. env/bin/activate                      && \
		python setup.py install                 && \
		nodeenv 4 -p --prebuilt                 && \
		nodeenv -p --node=system

tests: clean test1 clean test2 clean test3 clean test4 clean test5 clean

contributors:
	@echo "Nodeenv is written and maintained by Eugene Kalinin." > AUTHORS
	@echo "" >> AUTHORS
	@echo "Patches and Suggestions" >> AUTHORS
	@echo '```````````````````````' >> AUTHORS
	@echo "" >> AUTHORS
	@git log --raw | grep "^Author: " | \
		sort | uniq -c | sort -n -r | \
		cut -d ':' -f 2 | sed 's/^/- /' | \
		cut -d '<' -f1 | uniq | tail -n +3 >> AUTHORS
