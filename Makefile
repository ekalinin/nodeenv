.PHONY: default deploy deploy-github deploy-pypi update-pypi clean tests env
PYTHON=python3
TEST_ENV=env
DEV_TEST_ENV=env-dev
SETUP=pip install -U pip setuptools && $(PYTHON) setup.py install > /dev/null

default:
	: do nothing when dpkg-buildpackage runs this project Makefile

deploy-github:
	git tag `grep "nodeenv_version =" nodeenv.py | grep -o -E '[0-9]\.[0-9]{1,2}\.[0-9]{1,2}'`
	git push --tags origin master

deploy-pypi:
	rm -rf dist
	@. ${DEV_TEST_ENV}/bin/activate && \
		pip install -U setuptools wheel twine && \
		$(PYTHON) setup.py sdist bdist_wheel && \
		twine upload --repository pypi dist/*

update-pypi:
	$(PYTHON) setup.py register

deploy: contributors ut deploy-github deploy-pypi

clean:
	@rm -rf nodeenv.egg-info/
	@rm -rf dist/
	@rm -rf build/
	@rm -rf ${TEST_ENV}/
	@rm -rf nodeenv/

clean-test-env:
	@rm -rf ${TEST_ENV}

# https://virtualenv.pypa.io/en/legacy/reference.html#cmdoption-no-site-packages
# https://github.com/pypa/virtualenv/issues/1681
setup-test-env:
	@virtualenv ${TEST_ENV} > /dev/null 2>&1

env: clean-test-env setup-test-env
	@. ${TEST_ENV}/bin/activate                && \
		$(PYTHON) setup.py install

# https://virtualenv.pypa.io/en/legacy/reference.html#cmdoption-no-site-packages
# https://github.com/pypa/virtualenv/issues/1681
env-dev:
	@rm -rf ${DEV_TEST_ENV}                           && \
		$(PYTHON) -m venv ${DEV_TEST_ENV}             && \
		. ${DEV_TEST_ENV}/bin/activate                && \
		pip install -r requirements-dev.txt

test1: clean clean-test-env setup-test-env
	@echo " ="
	@echo " = test1: separate nodejs's env"
	@echo " ="
	@. ${TEST_ENV}/bin/activate           && \
		${SETUP}           				  && \
		nodeenv -j 4 nodeenv

test2: clean clean-test-env setup-test-env
	@echo " ="
	@echo " = test2: the same virtualenv's env, with 4 jobs"
	@echo " ="
	@. ${TEST_ENV}/bin/activate           && \
		${SETUP}           				  && \
		nodeenv -j 4 -p

test3: clean clean-test-env setup-test-env
	@echo " ="
	@echo " = test3: the same virtualenv's env, without any params"
	@echo " ="
	@. ${TEST_ENV}/bin/activate           && \
		${SETUP}           				  && \
		nodeenv -p

# https://github.com/ekalinin/nodeenv/issues/43
test4: clean clean-test-env
	@echo " ="
	@echo " = test4: system nodejs's for python3.9"
	@echo " ="
	@virtualenv --python=python3.9 ${TEST_ENV}    			    && \
		. ${TEST_ENV}/bin/activate                              && \
		${SETUP}           				  						&& \
		nodeenv -p --node=system

test5: clean clean-test-env
	@echo " ="
	@echo " = test5: prebuilt nodejs's env for python2"
	@echo " ="
	@virtualenv --python=python2.7 ${TEST_ENV}  && \
		. ${TEST_ENV}/bin/activate              && \
		${SETUP}           				  		&& \
		nodeenv -p --prebuilt

test7: clean clean-test-env setup-test-env
	@echo " ="
	@echo " = test7: freeze for global installation"
	@echo " ="
	@. ${TEST_ENV}/bin/activate           && \
		${SETUP}                          && \
		nodeenv -j 4 -p --prebuilt        && \
		. ${TEST_ENV}/bin/activate        && \
		npm install -g sitemap 			  && \
		npm -v                            && \
		node -v                           && \
		test "`freeze | grep -v corepack | wc -l`" = "       1";

test8: clean clean-test-env setup-test-env
	@echo " ="
	@echo " = test8: unicode paths, #49"
	@echo " ="
	@. ${TEST_ENV}/bin/activate           && \
		${SETUP}                          && \
		rm -rf öäü && mkdir öäü && cd öäü && \
		nodeenv -j 4 --prebuilt env       && \
		rm -rf öäü

test9: clean clean-test-env setup-test-env
	@echo " ="
	@echo " = test9: unicode paths, #187"
	@echo " ="
	@. ${TEST_ENV}/bin/activate                   			   && \
		${SETUP}           				  					   && \
		rm -rf "test dir" && mkdir "test dir" && cd "test dir" && \
		nodeenv -j 4 --prebuilt env       && \
		rm -rf "test dir"

test10: clean clean-test-env setup-test-env
	@echo " ="
	@echo " = test10: symlink does not fail if npm already exists, #189"
	@echo " ="
	@. ${TEST_ENV}/bin/activate           && \
		${SETUP}           				  && \
		nodeenv -j 4 -p --prebuilt        && \
		nodeenv -j 4 -p --prebuilt

tests: test1 test2 test3 test4 test7 test8 test9 test10 clean

ut: env-dev
	@. ${DEV_TEST_ENV}/bin/activate && tox -e py314

coverage: env-dev
	@. ${DEV_TEST_ENV}/bin/activate && \
		coverage run -p -m pytest && \
		coverage report -m && \
		coverage html

contributors:
	@echo "Nodeenv is written and maintained by Eugene Kalinin." > AUTHORS
	@echo "" >> AUTHORS
	@echo "Patches and Suggestions" >> AUTHORS
	@echo '```````````````````````' >> AUTHORS
	@echo "" >> AUTHORS
	@git log --raw | grep "^Author: " | \
		sort | uniq -c | sort -n -r | \
		cut -d ':' -f 2 | sed 's/^/- /' | \
		cut -d '<' -f1 | uniq | grep -v Kalinin | sed 's/ *$$//g' >> AUTHORS
