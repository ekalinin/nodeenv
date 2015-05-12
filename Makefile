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

test1:
	@echo " ="
	@echo " = test1: separate nodejs's env"
	@echo " ="
	@rm -rf env                           && \
		virtualenv --no-site-packages env && \
		. env/bin/activate                && \
		python setup.py install           && \
		rm -rf nodeenv                    && \
		nodeenv -j 4 nodeenv

test2:
	@echo " ="
	@echo " = test2: the same virtualenv's env, with 4 jobs"
	@echo " ="
	@rm -rf env                           && \
		virtualenv --no-site-packages env && \
		. env/bin/activate                && \
		python setup.py install           && \
		nodeenv -j 4 -p

test3:
	@echo " ="
	@echo " = test3: the same virtualenv's env, without any params"
	@echo " ="
	@rm -rf env                           && \
		virtualenv --no-site-packages env && \
		. env/bin/activate                && \
		python setup.py install           && \
		nodeenv -p

# https://github.com/ekalinin/nodeenv/issues/43
test4:
	@echo " ="
	@echo " = test4: separate nodejs's env for python3.4"
	@echo " ="
	@rm -rf env                                                 && \
		virtualenv --no-site-packages --python=python3.4 env    && \
		. env/bin/activate                                      && \
		python setup.py install                                 && \
		nodeenv 4 -p --prebuilt                                 && \
		nodeenv -p --node=system

test5:
	@echo " ="
	@echo " = test5: prebuilt nodejs's env for python2"
	@echo " ="
	@rm -rf env                                 && \
		virtualenv --no-site-packages --python=python2.7 env    && \
		. env/bin/activate                      && \
		python setup.py install                 && \
		nodeenv 4 -p --prebuilt                 && \
		nodeenv -p --node=system

test6:
	@echo " ="
	@echo " = test6: separate iojs's env"
	@echo " ="
	@rm -rf env                           && \
		virtualenv --no-site-packages env && \
		. env/bin/activate                && \
		python setup.py install           && \
		nodeenv -p --prebuilt --iojs

test7:
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
		test "`freeze | wc -l`" = "1";

tests: clean test1 clean test2 clean test3 clean test4 clean test5 test6 test7 clean

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
