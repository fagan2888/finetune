import tensorflow as tf	
from finetune.util.shapes import shape_list


def embed_context(context, featurizer_state, config, train):
    with tf.variable_scope("context_embedding"):
        context_dim = shape_list(context)[-1]
        context_weight = tf.get_variable(
            name="ce",	
            shape=[context_dim, config.n_context_embed],
            initializer=tf.random_normal_initializer(stddev=config.context_embed_stddev),	
        )
        context_bias = tf.get_variable(
            name="ca",	
            shape=[config.n_context_embed],	
            initializer=tf.zeros_initializer(),	
        )
        c_embed = tf.add(tf.tensordot(context, context_weight, axes=[[-1], [0]]), context_bias)
    featurizer_state['context'] = c_embed
    return featurizer_state


def add_context_embed(featurizer_state):
    if "context" in featurizer_state:
        context_embed = featurizer_state["context"]

        shape = shape_list(context_embed)
        if len(shape) == 4:
            # comparison / multiple choice 
            flat_embed = tf.reshape(
                context_embed, 
                [shape[0] * shape[1], shape[2], shape[3]],
            )
        else:
            flat_embed = context_embed

        seq_mask = tf.sequence_mask(featurizer_state['lengths'])
        for key in ['features', 'explain_out']:
            if key in featurizer_state:
                float_mask = tf.cast(seq_mask, tf.float32)
                binary_mask = tf.constant(1.) - float_mask
                flat_embed = flat_embed * tf.expand_dims(binary_mask, -1)
                sum_context = tf.reduce_sum(flat_embed, 1)
                mean_context = sum_context / tf.reduce_sum(float_mask)

                if len(shape) == 4:
                    mean_context = tf.reshape(
                        mean_context, 
                        [shape[0], shape[1], shape[3]]
                    )
    
                featurizer_state[key] = tf.concat(
                    (featurizer_state[key], mean_context), -1
                )

        featurizer_state['sequence_features'] = tf.concat(
            (featurizer_state['sequence_features'], context_embed), -1
        )


def pairwise_embed_context(context, featurizer_state, config, train):
    with tf.variable_scope("context_attn_embedding"):
        context_dim = shape_list(context)[-1]
        seq_mask = tf.sequence_mask(featurizer_state['lengths'], maxlen=config.max_length)
        sq_mask = tf.expand_dims(seq_mask, 1) & tf.expand_dims(seq_mask, 2)
        heads_sq_mask = tf.stack([sq_mask] * 16, axis=1) 
        tf.summary.histogram('context 0', context[:,:,0][seq_mask])
        diff = tf.abs(tf.expand_dims(context, 1) - tf.expand_dims(context, 2))
        tf.summary.histogram('specific doc diff', diff[0,:,:][sq_mask[0,:,:]])

        g = tf.get_variable(
            name='g',
            shape=[1, config.n_heads, 1, 1, context_dim],
            initializer=tf.random_normal_initializer(mean=1.0, stddev=0.5)
        )
        b = tf.get_variable(
            name='b',
            shape=[1, config.n_heads, 1, 1, context_dim],
            initializer=tf.constant_initializer(0.2)
        )
        tf.summary.histogram('g', g)
        tf.summary.histogram('b', b)
        tf.summary.histogram('diff', diff[sq_mask])
        proximity = tf.nn.relu(tf.expand_dims(-diff, axis=1) * g + b)
        tf.summary.histogram('proximity', proximity[heads_sq_mask])
        total_offset = tf.reduce_sum(proximity, axis=-1, keep_dims=False) 
        tf.summary.histogram('mean_offset', total_offset[heads_sq_mask])
    featurizer_state['context'] = total_offset
