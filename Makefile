.PHONY: default deploy deploy-github deploy-pypi update-pypi clean tests env

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

env:
	@rm -rf env                           && \
		virtualenv --no-site-packages env && \
		. env/bin/activate                && \
		python setup.py install

env-dev:
	@rm -rf env-dev                           && \
		virtualenv --no-site-packages env-dev && \
		. env-dev/bin/activate                && \
		pip install -r requirements-dev.txt

test1: clean
	@echo " ="
	@echo " = test1: separate nodejs's env"
	@echo " ="
	@rm -rf env                           && \
		virtualenv --no-site-packages env && \
		. env/bin/activate                && \
		python setup.py install           && \
		rm -rf nodeenv                    && \
		nodeenv -j 4 nodeenv

test2: clean
	@echo " ="
	@echo " = test2: the same virtualenv's env, with 4 jobs"
	@echo " ="
	@rm -rf env                           && \
		virtualenv --no-site-packages env && \
		. env/bin/activate                && \
		python setup.py install           && \
		nodeenv -j 4 -p

test3: clean
	@echo " ="
	@echo " = test3: the same virtualenv's env, without any params"
	@echo " ="
	@rm -rf env                           && \
		virtualenv --no-site-packages env && \
		. env/bin/activate                && \
		python setup.py install           && \
		nodeenv -p

# https://github.com/ekalinin/nodeenv/issues/43
test4: clean
	@echo " ="
	@echo " = test4: system nodejs's for python3.5"
	@echo " ="
	@rm -rf env                                                 && \
		virtualenv --no-site-packages --python=python3.5 env    && \
		. env/bin/activate                                      && \
		python setup.py install                                 && \
		nodeenv -p --node=system

test5: clean
	@echo " ="
	@echo " = test5: prebuilt nodejs's env for python2"
	@echo " ="
	@rm -rf env                                 && \
		virtualenv --no-site-packages --python=python2.7 env    && \
		. env/bin/activate                      && \
		python setup.py install                 && \
		nodeenv -p --prebuilt

test6: clean
	@echo " ="
	@echo " = test6: separate iojs's env"
	@echo " ="
	@rm -rf env                           && \
		virtualenv --no-site-packages env && \
		. env/bin/activate                && \
		python setup.py install           && \
		nodeenv -p --prebuilt --iojs

test7: clean
	@echo " ="
	@echo " = test7: freeze for global installation"
	@echo " ="
	@rm -rf env                           && \
		virtualenv --no-site-packages env && \
		. env/bin/activate                && \
		python setup.py install           && \
		nodeenv -j 4 -p --prebuilt        && \
		. env/bin/activate                && \
		npm install -g sitemap 			  && \
		npm -v                            && \
		node -v                           && \
		test "`freeze | wc -l`" = "1";

test8: clean
	@echo " ="
	@echo " = test8: unicode paths, #49"
	@echo " ="
	@rm -rf env                           && \
		virtualenv --no-site-packages env && \
		. env/bin/activate                && \
		python setup.py install           && \
		rm -rf öäü && mkdir öäü && cd öäü && \
		nodeenv -j 4 --prebuilt env       && \
		rm -rf öäü

test9: clean
	@echo " ="
	@echo " = test9: unicode paths, #187"
	@echo " ="
	@rm -rf env                           && \
		virtualenv --no-site-packages env && \
		. env/bin/activate                && \
		python setup.py install           && \
		rm -rf "test dir" && mkdir "test dir" && cd "test dir" && \
		nodeenv -j 4 --prebuilt env       && \
		rm -rf "test dir"

tests: clean test1 test2 test3 test4 test5 test7 test8 test9 clean

ut: env-dev
	@. env-dev/bin/activate && tox -e py27

contributors:
	@echo "Nodeenv is written and maintained by Eugene Kalinin." > AUTHORS
	@echo "" >> AUTHORS
	@echo "Patches and Suggestions" >> AUTHORS
	@echo '```````````````````````' >> AUTHORS
	@echo "" >> AUTHORS
	@git log --raw | grep "^Author: " | \
		sort | uniq -c | sort -n -r | \
		cut -d ':' -f 2 | sed 's/^/- /' | \
		cut -d '<' -f1 | uniq | grep -v Kalinin >> AUTHORS
