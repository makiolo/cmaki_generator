if [[ ! -d node_modules/cmaki_generator ]]; then
	mkdir -p node_modules/cmaki_generator
	(cd node_modules && git clone https://github.com/makiolo/cmaki_generator.git)
	(cd node_modules/cmaki_generator && rm -Rf .git)
fi
